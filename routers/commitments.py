import logging
from datetime import date as date_type
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

import commitment_service
from auth import get_current_user
from db import get_db
from models import Client, Commitment, Group, GroupMembership, User

router = APIRouter(prefix="/api/v1", tags=["commitments"])

logger = logging.getLogger(__name__)


def _require_group_member(user: User, group_id: int, db: Session) -> None:
    """main.py의 동명 함수와 같은 규칙. 라우터가 main을 import하면 순환이 되므로
    여기 둔다."""
    member = db.execute(
        select(GroupMembership).where(
            GroupMembership.user_id == user.id,
            GroupMembership.group_id == group_id,
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "COMMITMENT_ACCESS_FORBIDDEN",
                "message": "이 그룹에 접근할 수 없습니다",
            },
        )


def _ok(data, meta: dict | None = None):
    envelope = {"success": True, "data": data, "error": None}
    if meta is not None:
        envelope["meta"] = meta
    return envelope


def _raise_commitment_forbidden() -> None:
    raise HTTPException(
        status_code=403,
        detail={
            "code": "COMMITMENT_ACCESS_FORBIDDEN",
            "message": "이 그룹에 접근할 수 없습니다",
        },
    )


def _serialize_client(c: Client) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "created_at": c.created_at.isoformat(),
    }


class ClientCreateBody(BaseModel):
    group_id: int
    name: str


@router.get("/clients")
def list_clients(
    group_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_group_member(current_user, group_id, db)
    rows = db.execute(
        select(Client).where(Client.group_id == group_id).order_by(Client.name).offset(offset).limit(limit)
    ).scalars().all()
    return _ok([_serialize_client(c) for c in rows])


@router.post("/clients")
def create_client(
    body: ClientCreateBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_group_member(current_user, body.group_id, db)
    name = body.name.strip()
    if not name:
        raise HTTPException(
            status_code=400,
            detail={"code": "CLIENT_NAME_INVALID", "message": "클라이언트 이름이 비어 있습니다"},
        )

    existing = db.execute(
        select(Client).where(Client.group_id == body.group_id, Client.name == name)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={"code": "CLIENT_NAME_DUPLICATE", "message": "이미 등록된 클라이언트입니다"},
        )

    created = Client(group_id=body.group_id, name=name)
    db.add(created)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "CLIENT_NAME_DUPLICATE", "message": "이미 등록된 클라이언트입니다"},
        )
    db.refresh(created)
    return _ok(_serialize_client(created))


def _serialize_commitment(c: Commitment, client_name: str | None, today: date_type) -> dict:
    is_overdue, is_due_soon = commitment_service.due_flags(c, today)
    return {
        "id": c.id,
        "content": c.content,
        "client_id": c.client_id,
        "client_name": client_name,
        "due_date": c.due_date.isoformat() if c.due_date else None,
        "status": c.status,
        "source_type": c.source_type,
        "source_id": c.source_id,
        # 약속 카드에서 출처 대화방으로 건너뛰기 위한 값. 목록은 이미
        # visible_commitment_filter가 room_id로 걸러낸 뒤라, 여기서 내려도
        # 볼 수 없는 방의 id가 새지 않는다.
        "room_id": c.room_id,
        "evidence": c.evidence,
        "is_overdue": is_overdue,
        "is_due_soon": is_due_soon,
        "created_at": c.created_at.isoformat(),
    }


def _utc_iso(value: datetime | None) -> str | None:
    """tz를 반드시 붙여 내려보낸다.

    프론트가 이 값으로 "12분 전"을 계산한다. tz 없는 문자열을 JS의 Date가
    로컬시각으로 읽으면 KST 기준 9시간이 통째로 어긋난다. SQLite는 tz를
    떨어뜨리고 Postgres는 유지해서, 환경에 따라 결과가 갈리는 자리다.
    """
    if value is None:
        return None
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).isoformat()


def _sweep_meta(db: Session, group_id: int) -> dict:
    """방금 끝난 스윕이 무엇을 했는지. 화면에 "12분 전 · 대화 34개에서 2건 찾음"을
    띄우기 위한 값이다.

    스윕은 조용히 돌아서, 사용자 입장에서는 약속이 어느 날 그냥 생겨 있다.
    누가 언제 무엇을 보고 만든 건지 보이지 않으면 목록을 믿기 어렵다.

    아직 안 돌았으면 세 값 모두 None이다. 0으로 내리지 않는 이유는 "훑었는데
    아무것도 못 찾음"과 구분되어야 하기 때문이다.

    last_at은 쿨다운 표식(Group.last_swept_at)이 아니라 실제로 대화를 읽은
    시각이다. 쿨다운은 훑을 게 없어도 갱신돼서, 그 값을 개수 옆에 붙이면
    "방금 · 대화 34개에서 2건"처럼 며칠 전 성과가 방금 일처럼 읽힌다.
    """
    row = db.execute(
        select(Group.last_scan_at, Group.last_sweep_scanned, Group.last_sweep_found)
        .where(Group.id == group_id)
    ).one()
    return {
        "last_at": _utc_iso(row.last_scan_at),
        "scanned": row.last_sweep_scanned,
        "found": row.last_sweep_found,
        # 예산은 그룹이 아니라 서버 전체가 나눠 쓴다. 남은 양이 보여야
        # "왜 오늘은 안 도는지"를 화면에서 설명할 수 있다.
        "budget_used": commitment_service.sweep_calls_used_today(db),
        "budget_total": commitment_service.SWEEP_DAILY_BUDGET,
    }


class StatusBody(BaseModel):
    status: str


class BulkStatusBody(BaseModel):
    ids: list[int] = Field(max_length=100)
    status: str


def _client_name(db: Session, client_id: int | None) -> str | None:
    if client_id is None:
        return None
    linked = db.get(Client, client_id)
    return linked.name if linked else None


@router.get("/commitments")
def list_commitments(
    group_id: int,
    status: str | None = None,
    client_id: int | None = None,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_group_member(current_user, group_id, db)
    try:
        commitment_service.maybe_sweep(db, group_id)
    except Exception:
        # 스윕은 부가 작업이다. 여기서 새는 예외로 조회 자체를 죽이지 않는다
        # (TS-019와 같은 봉투 없는 500 구멍). 실패한 트랜잭션 상태를 되돌려야
        # 아래 조회가 이어서 실행될 수 있다.
        db.rollback()
        logger.warning(
            "약속 스윕 호출 실패",
            extra={"event": "commitment.sweep.call_failed", "group_id": group_id},
            exc_info=True,
        )

    query = select(Commitment).where(Commitment.group_id == group_id)
    if status is not None:
        query = query.where(Commitment.status == status)
    if client_id is not None:
        query = query.where(Commitment.client_id == client_id)
    query = query.where(commitment_service.visible_commitment_filter(current_user.id))

    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = db.execute(
        query.order_by(Commitment.created_at.desc()).limit(limit)
    ).scalars().all()

    names = {
        c.id: c.name
        for c in db.execute(select(Client).where(Client.group_id == group_id))
        .scalars()
        .all()
    }
    today = commitment_service.today_kst()
    meta = {
        "total": total,
        "limit": limit,
        "hasNext": total > limit,
        "sweep": _sweep_meta(db, group_id),
    }
    return _ok(
        [_serialize_commitment(c, names.get(c.client_id), today) for c in rows], meta
    )


@router.post("/commitments/bulk-status")
def bulk_update_status(
    body: BulkStatusBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 중복 id(예: [1, 1])를 그대로 두면 updated 카운트가 요청 개수와
    # 어긋난다. 먼저 걸러서 이후 로직 전부가 고유 id만 다루게 한다.
    ids = set(body.ids)
    if not ids:
        return _ok({"updated": 0})

    rows = db.execute(
        select(Commitment).where(Commitment.id.in_(ids))
    ).scalars().all()
    if len(rows) != len(ids):
        raise HTTPException(
            status_code=404,
            detail={"code": "COMMITMENT_NOT_FOUND", "message": "약속을 찾을 수 없습니다"},
        )

    # 부분 성공은 무엇이 반영됐는지 알 수 없게 만든다. 하나라도 남의 것/안 보이는
    # 것이면 전부 거부한다. 그룹 소속 확인은 행마다가 아니라 고유 group_id마다
    # 한 번만 — 100개 id가 같은 그룹에 몰려도 SELECT는 한 번이면 충분하다.
    for group_id in {row.group_id for row in rows}:
        _require_group_member(current_user, group_id, db)
    for row in rows:
        if not commitment_service.is_commitment_visible(db, current_user.id, row):
            _raise_commitment_forbidden()
    for row in rows:
        if not commitment_service.can_transition(row.status, body.status):
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "COMMITMENT_STATUS_INVALID",
                    "message": f"{row.status}에서 {body.status}로 바꿀 수 없습니다",
                },
            )

    for row in rows:
        commitment_service.apply_status(row, body.status)
    db.commit()
    return _ok({"updated": len(rows)})


@router.patch("/commitments/{commitment_id}")
def update_commitment_status(
    commitment_id: int,
    body: StatusBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    found = db.get(Commitment, commitment_id)
    if found is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "COMMITMENT_NOT_FOUND", "message": "약속을 찾을 수 없습니다"},
        )
    _require_group_member(current_user, found.group_id, db)
    if not commitment_service.is_commitment_visible(db, current_user.id, found):
        _raise_commitment_forbidden()

    if not commitment_service.can_transition(found.status, body.status):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "COMMITMENT_STATUS_INVALID",
                "message": f"{found.status}에서 {body.status}로 바꿀 수 없습니다",
            },
        )
    commitment_service.apply_status(found, body.status)
    db.commit()
    db.refresh(found)
    return _ok(
        _serialize_commitment(
            found, _client_name(db, found.client_id), commitment_service.today_kst()
        )
    )
