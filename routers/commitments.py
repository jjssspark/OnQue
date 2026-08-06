from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

import commitment_service
from auth import get_current_user
from db import get_db
from models import Client, Commitment, GroupMembership, User

router = APIRouter(prefix="/api/v1", tags=["commitments"])


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


def _ok(data):
    return {"success": True, "data": data, "error": None}


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
    ids: list[int]
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
    commitment_service.maybe_sweep(db, group_id)

    query = select(Commitment).where(Commitment.group_id == group_id)
    if status is not None:
        query = query.where(Commitment.status == status)
    if client_id is not None:
        query = query.where(Commitment.client_id == client_id)
    rows = db.execute(
        query.order_by(Commitment.created_at.desc()).limit(limit)
    ).scalars().all()

    names = {
        c.id: c.name
        for c in db.execute(select(Client).where(Client.group_id == group_id))
        .scalars()
        .all()
    }
    today = date_type.today()
    return _ok([_serialize_commitment(c, names.get(c.client_id), today) for c in rows])


@router.post("/commitments/bulk-status")
def bulk_update_status(
    body: BulkStatusBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not body.ids:
        return _ok({"updated": 0})

    rows = db.execute(
        select(Commitment).where(Commitment.id.in_(body.ids))
    ).scalars().all()
    if len(rows) != len(set(body.ids)):
        raise HTTPException(
            status_code=404,
            detail={"code": "COMMITMENT_NOT_FOUND", "message": "약속을 찾을 수 없습니다"},
        )

    # 부분 성공은 무엇이 반영됐는지 알 수 없게 만든다. 하나라도 남의 것이면 전부 거부한다.
    for row in rows:
        _require_group_member(current_user, row.group_id, db)
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
    return _ok(_serialize_commitment(found, _client_name(db, found.client_id), date_type.today()))
