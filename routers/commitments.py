import logging
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

import commitment_service
from auth import get_current_user
from db import get_db
from models import ChatMessage, ChatRoomMember, Client, Commitment, GroupMembership, User

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


def _visible_commitment_filter(user_id: int):
    """채팅방은 그룹 전원이 아니라 초대된 사람만 볼 수 있다(main.py:588
    _require_room_access와 같은 규칙). 하지만 스윕은 그룹의 모든 방을 훑어
    Commitment.evidence에 원문을 그대로 저장하므로, 조회 시점에 방 멤버십으로
    걸러야 비공개 방의 대화가 그룹 전원에게 새지 않는다.

    call/document 출처는 방 개념이 없으므로 그대로 통과시킨다. source_id가
    NULL인 채팅 출처는 어느 방인지 확인할 수 없으므로 fail-closed로 숨긴다
    (IN (subquery)는 NULL에 대해 NULL/false로 평가되어 자연히 걸러진다).
    """
    allowed_rooms = select(ChatRoomMember.room_id).where(ChatRoomMember.user_id == user_id)
    return or_(
        Commitment.source_type != "chat",
        Commitment.source_id.in_(
            select(ChatMessage.id).where(ChatMessage.room_id.in_(allowed_rooms))
        ),
    )


def _is_commitment_visible(db: Session, user_id: int, commitment: Commitment) -> bool:
    """단건(PATCH)·소수건(bulk) 판정용. 목록 필터(_visible_commitment_filter)와
    같은 규칙을 단일 레코드에 적용한다."""
    if commitment.source_type != "chat":
        return True
    if commitment.source_id is None:
        return False
    room_id = db.execute(
        select(ChatMessage.room_id).where(ChatMessage.id == commitment.source_id)
    ).scalar_one_or_none()
    if room_id is None:
        return False
    return db.get(ChatRoomMember, {"room_id": room_id, "user_id": user_id}) is not None


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
        "evidence": c.evidence,
        "is_overdue": is_overdue,
        "is_due_soon": is_due_soon,
        "created_at": c.created_at.isoformat(),
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
    query = query.where(_visible_commitment_filter(current_user.id))

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
    meta = {"total": total, "limit": limit, "hasNext": total > limit}
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
        if not _is_commitment_visible(db, current_user.id, row):
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
    if not _is_commitment_visible(db, current_user.id, found):
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
