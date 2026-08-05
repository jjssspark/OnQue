from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import get_current_user
from db import get_db
from models import DEFAULT_CHAT_ROOM_NAME, ChatRoom, Group, GroupMembership, User

router = APIRouter(prefix="/api/v1", tags=["groups"])


def _require_admin(user: User) -> None:
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": "GROUP_CREATE_FORBIDDEN", "message": "관리자만 가능한 작업입니다."},
        )


def get_user_groups(user_id: int, db: Session) -> list[Group]:
    memberships = db.scalars(
        select(GroupMembership).where(GroupMembership.user_id == user_id)
    ).all()
    group_ids = [m.group_id for m in memberships]
    return db.scalars(select(Group).where(Group.id.in_(group_ids))).all() if group_ids else []


class GroupCreateBody(BaseModel):
    name: str


class GroupMemberBody(BaseModel):
    user_id: int


@router.post("/groups")
def create_group(
    body: GroupCreateBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    group = Group(name=body.name, created_by=current_user.id)
    db.add(group)
    db.commit()
    db.refresh(group)
    db.add(GroupMembership(user_id=current_user.id, group_id=group.id))
    db.add(
        ChatRoom(
            group_id=group.id, name=DEFAULT_CHAT_ROOM_NAME, created_by=current_user.id
        )
    )
    db.commit()
    return {"success": True, "data": {"id": group.id, "name": group.name}, "error": None}


@router.get("/groups")
def list_my_groups(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    groups = get_user_groups(current_user.id, db)
    return {
        "success": True,
        "data": [{"id": g.id, "name": g.name} for g in groups],
        "error": None,
    }


@router.get("/groups/{group_id}/members")
def list_group_members(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(
            status_code=404, detail={"code": "GROUP_NOT_FOUND", "message": "그룹을 찾을 수 없습니다."}
        )
    # 관리자가 아니면 자신이 속한 그룹의 명단만 볼 수 있다.
    if current_user.role != "admin":
        is_member = db.get(
            GroupMembership, {"user_id": current_user.id, "group_id": group_id}
        )
        if not is_member:
            raise HTTPException(
                status_code=403,
                detail={"code": "GROUP_ACCESS_FORBIDDEN", "message": "이 그룹에 접근할 수 없습니다."},
            )

    memberships = db.scalars(
        select(GroupMembership).where(GroupMembership.group_id == group_id)
    ).all()
    user_ids = [m.user_id for m in memberships]
    users = (
        db.scalars(select(User).where(User.id.in_(user_ids))).all() if user_ids else []
    )
    return {
        "success": True,
        "data": [
            {"id": u.id, "email": u.email, "name": u.name, "role": u.role} for u in users
        ],
        "error": None,
    }


@router.post("/groups/{group_id}/members")
def add_group_member(
    group_id: int,
    body: GroupMemberBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": "GROUP_MEMBER_ADD_FORBIDDEN", "message": "관리자만 가능한 작업입니다."},
        )
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(
            status_code=404, detail={"code": "GROUP_NOT_FOUND", "message": "그룹을 찾을 수 없습니다."}
        )
    target_user = db.get(User, body.user_id)
    if not target_user:
        raise HTTPException(
            status_code=404, detail={"code": "USER_NOT_FOUND", "message": "사용자를 찾을 수 없습니다."}
        )
    existing = db.get(GroupMembership, {"user_id": body.user_id, "group_id": group_id})
    if not existing:
        db.add(GroupMembership(user_id=body.user_id, group_id=group_id))
        db.commit()
    return {"success": True, "data": {"group_id": group_id, "user_id": body.user_id}, "error": None}


@router.delete("/groups/{group_id}/members/{user_id}")
def remove_group_member(
    group_id: int,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": "GROUP_MEMBER_ADD_FORBIDDEN", "message": "관리자만 가능한 작업입니다."},
        )
    membership = db.get(GroupMembership, {"user_id": user_id, "group_id": group_id})
    if membership:
        db.delete(membership)
        db.commit()
    return {"success": True, "data": {"deleted": True}, "error": None}
