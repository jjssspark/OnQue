"""약속 추출 결과를 DB에 반영하는 계층.

라우터와 요약 파이프라인 양쪽에서 쓰이므로 별도 모듈로 둔다.
"""

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

import gemini_service
from models import ChatMessage, ChatRoom, Client, Commitment, Group, COMMITMENT_STATUSES

logger = logging.getLogger(__name__)

# 기한 경고 기준. D-2 이내면 임박으로 본다.
DUE_SOON_DAYS = 2

# 다이어그램에 그려진 화살표만 허용한다: proposed -> confirmed/dismissed,
# confirmed -> fulfilled/dismissed. fulfilled·dismissed는 키가 없으므로
# 종료 상태에서는 어떤 target이 와도 자연히 거부된다 — 되돌리기(undo)는 없다.
_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "proposed": frozenset({"confirmed", "dismissed"}),
    "confirmed": frozenset({"fulfilled", "dismissed"}),
}


def can_transition(current: str, target: str) -> bool:
    if target not in COMMITMENT_STATUSES:
        return False
    return target in _ALLOWED_TRANSITIONS.get(current, frozenset())


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


SWEEP_COOLDOWN_MINUTES = 10
# 이보다 적게 쌓인 방은 훑지 않는다. 한산한 방은 영영 안 훑일 수 있으나,
# 그런 방에서 놓칠 약속은 적고 사용자는 명령어로 직접 부를 수 있다.
CHAT_SCAN_THRESHOLD = 15
# 한 번에 프롬프트에 실을 메시지 상한. 오래 밀린 방을 통째로 넣으면 토큰
# 한도로 실패하고, 실패 시 포인터를 전진시키지 않으므로 같은 실패가 매
# 스윕마다 반복된다. 상한을 두면 밀린 방도 스윕을 거듭하며 조금씩 따라잡는다.
CHAT_SCAN_BATCH_LIMIT = 100


def _scan_room(db: Session, room: ChatRoom) -> bool:
    """방 하나를 훑는다. 실제로 스캔했으면 True.

    실패하면 예외를 그대로 던진다. 삼키지 않는 이유는 호출자(maybe_sweep)가
    방 단위로 격리해서 잡아야 이 방의 실패가 다른 방에 번지지 않기 때문이다.
    """
    query = select(ChatMessage).where(ChatMessage.room_id == room.id)
    if room.last_scanned_message_id is not None:
        query = query.where(ChatMessage.id > room.last_scanned_message_id)
    messages = (
        db.execute(query.order_by(ChatMessage.id).limit(CHAT_SCAN_BATCH_LIMIT))
        .scalars()
        .all()
    )

    if len(messages) < CHAT_SCAN_THRESHOLD:
        return False

    history = "\n".join(f"{m.sender}: {m.content}" for m in messages)
    items = gemini_service.extract_chat_commitments(history)
    if items is None:
        # 모델 호출/파싱이 실패했다. "약속 없음"과 구분해 포인터를 전진시키지
        # 않아야 다음 스윕에서 같은 배치를 다시 시도한다.
        raise RuntimeError(f"채팅 약속 추출 실패: room_id={room.id}")

    create_commitments(
        db,
        group_id=room.group_id,
        items=items,
        source_type="chat",
        source_id=messages[-1].id,
    )
    room.last_scanned_message_id = messages[-1].id
    return True


def maybe_sweep(db: Session, group_id: int) -> int:
    """요청에 편승해 돌리는 자율 점검. 스캔한 방 수를 돌려준다.

    Render 무료 티어에 상주 워커가 없어 백그라운드 스케줄러를 쓸 수 없다.
    아무도 접속하지 않으면 스윕도 안 돌지만, 그때는 알림을 볼 사람도 없다.

    방은 서로 독립적으로 처리한다. 한 방의 실패가 다른 방의 결과나
    last_swept_at 갱신까지 함께 날려버리면, 문제 있는 방 하나가 그룹 전체의
    약속 탐지를 영구히 막고 쿨다운까지 무력화해 매 요청마다 전체를
    재시도하게 만든다.
    """
    group = db.get(Group, group_id)
    if group is None:
        return 0

    now = datetime.now(timezone.utc)
    if group.last_swept_at is not None:
        last = group.last_swept_at
        # SQLite는 tz 정보를 잃어버린다. UTC로 간주하고 비교한다.
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if now - last < timedelta(minutes=SWEEP_COOLDOWN_MINUTES):
            return 0

    rooms = db.execute(
        select(ChatRoom).where(ChatRoom.group_id == group_id)
    ).scalars().all()

    scanned = 0
    for room in rooms:
        try:
            if _scan_room(db, room):
                db.commit()
                scanned += 1
        except Exception:
            db.rollback()
            logger.warning(
                "방 스캔 실패",
                extra={
                    "event": "commitment.sweep.room_failed",
                    "group_id": group_id,
                    "room_id": room.id,
                },
                exc_info=True,
            )

    # last_swept_at은 스윕을 "시도했다"는 기록이지 "성공했다"는 기록이
    # 아니다. 방이 전부 실패하거나 임계값을 못 넘겨도 쿨다운은 정상적으로
    # 다시 걸려야 매 요청마다 그룹 전체를 재시도하는 일이 없다.
    group.last_swept_at = now
    db.commit()

    return scanned
