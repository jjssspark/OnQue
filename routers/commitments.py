from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from auth import get_current_user
from db import get_db
from models import Client, GroupMembership, User

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
