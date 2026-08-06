"""약속 추출 결과를 DB에 반영하는 계층.

라우터와 요약 파이프라인 양쪽에서 쓰이므로 별도 모듈로 둔다.
"""

import logging
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Client, Commitment, COMMITMENT_STATUSES

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = frozenset({"fulfilled", "dismissed"})

# 기한 경고 기준. D-2 이내면 임박으로 본다.
DUE_SOON_DAYS = 2


def can_transition(current: str, target: str) -> bool:
    """종료 상태에서는 빠져나오지 못한다. 잘못 눌렀다면 새 약속을 만든다."""
    if target not in COMMITMENT_STATUSES:
        return False
    if current in TERMINAL_STATUSES:
        return False
    return current != target


def apply_status(commitment: Commitment, target: str) -> None:
    commitment.status = target
    if target == "confirmed" and commitment.confirmed_at is None:
        commitment.confirmed_at = datetime.now(timezone.utc)


def due_flags(commitment: Commitment, today: date) -> tuple[bool, bool]:
    """(is_overdue, is_due_soon). 저장하지 않고 조회 시 계산하는 파생값이다.

    proposed 상태는 아직 사람이 확인하지 않았으므로 추적 대상이 아니다.
    """
    if commitment.status != "confirmed" or commitment.due_date is None:
        return (False, False)
    delta = (commitment.due_date - today).days
    return (delta < 0, 0 <= delta <= DUE_SOON_DAYS)


def _parse_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def resolve_client_id(db: Session, group_id: int, client_name: str) -> int | None:
    """모델이 말한 클라이언트명을 등록된 Client와 대조한다.

    없으면 None을 돌려주고 새로 만들지 않는다. 오탈자와 환각이 클라이언트
    목록을 오염시키기 때문이다. 클라이언트 생성은 사람이 한다.
    """
    name = (client_name or "").strip()
    if not name:
        return None
    found = db.execute(
        select(Client).where(Client.group_id == group_id, Client.name == name)
    ).scalar_one_or_none()
    return found.id if found else None


def create_commitments(
    db: Session,
    group_id: int,
    items: list[dict],
    source_type: str,
    source_id: int | None,
) -> list[Commitment]:
    """추출된 약속을 proposed 상태로 저장한다. commit은 호출자가 한다."""
    created: list[Commitment] = []
    for item in items:
        content = (item.get("content") or "").strip()
        evidence = (item.get("evidence") or "").strip()
        if not content or not evidence:
            continue
        commitment = Commitment(
            group_id=group_id,
            client_id=resolve_client_id(db, group_id, item.get("client_name", "")),
            content=content,
            due_date=_parse_date(item.get("due_date") or ""),
            status="proposed",
            source_type=source_type,
            source_id=source_id,
            evidence=evidence,
        )
        db.add(commitment)
        created.append(commitment)
    return created
