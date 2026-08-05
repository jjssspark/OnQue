from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from auth import get_current_user
from db import get_db
from models import (
    DEFAULT_CHAT_ROOM_NAME,
    ChatRoom,
    ChatRoomMember,
    Group,
    GroupInvitation,
    GroupMembership,
    User,
)

router = APIRouter(prefix="/api/v1", tags=["groups"])


def _require_admin(user: User) -> None:
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": "GROUP_CREATE_FORBIDDEN", "message": "관리자만 가능한 작업입니다."},
        )


def join_group(db: Session, user_id: int, group_id: int) -> None:
    """그룹에 합류시킨다. 커밋은 호출부가 한다.

    기본 방까지 넣어야 합류 직후 채팅 화면이 빈 목록이 아니다. 나머지 주제별
    방은 그 방에 있는 사람이 초대하게 둔다.
    """
    if db.get(GroupMembership, {"user_id": user_id, "group_id": group_id}):
        return

    db.add(GroupMembership(user_id=user_id, group_id=group_id))
    default_room = db.scalars(
        select(ChatRoom)
        .where(ChatRoom.group_id == group_id, ChatRoom.name == DEFAULT_CHAT_ROOM_NAME)
        .order_by(ChatRoom.created_at.asc())
        .limit(1)
    ).first()
    if default_room and not db.get(
        ChatRoomMember, {"room_id": default_room.id, "user_id": user_id}
    ):
        db.add(ChatRoomMember(room_id=default_room.id, user_id=user_id))


def get_user_groups(user_id: int, db: Session) -> list[Group]:
    memberships = db.scalars(
        select(GroupMembership).where(GroupMembership.user_id == user_id)
    ).all()
    group_ids = [m.group_id for m in memberships]
    return db.scalars(select(Group).where(Group.id.in_(group_ids))).all() if group_ids else []


class GroupCreateBody(BaseModel):
    name: str


class GroupInviteBody(BaseModel):
    email: EmailStr


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
    room = ChatRoom(
        group_id=group.id, name=DEFAULT_CHAT_ROOM_NAME, created_by=current_user.id
    )
    db.add(room)
    db.flush()
    db.add(ChatRoomMember(room_id=room.id, user_id=current_user.id))
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
    join_group(db, body.user_id, group_id)
    db.commit()
    return {"success": True, "data": {"group_id": group_id, "user_id": body.user_id}, "error": None}


def _serialize_invitation(inv: GroupInvitation) -> dict:
    return {
        "id": inv.id,
        "group_id": inv.group_id,
        "email": inv.email,
        "invited_by": inv.invited_by,
        "created_at": inv.created_at.isoformat(),
        "accepted_at": inv.accepted_at.isoformat() if inv.accepted_at else None,
    }


def _upsert_invitation(
    db: Session, group_id: int, email: str, invited_by: int, accepted: bool
) -> GroupInvitation:
    """(group_id, email)에 유니크 제약이 있어 같은 사람을 다시 초대해도 행은 하나다."""
    inv = db.scalar(
        select(GroupInvitation).where(
            GroupInvitation.group_id == group_id, GroupInvitation.email == email
        )
    )
    if inv is None:
        inv = GroupInvitation(group_id=group_id, email=email, invited_by=invited_by)
        db.add(inv)
    else:
        inv.invited_by = invited_by
    inv.accepted_at = datetime.now(timezone.utc) if accepted else None
    db.flush()
    return inv


@router.post("/groups/{group_id}/invitations")
def invite_to_group_by_email(
    group_id: int,
    body: GroupInviteBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """이메일로 초대한다. 아직 가입 전이면 대기 상태로 남고, 가입 시 자동 합류한다."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": "GROUP_INVITE_FORBIDDEN", "message": "관리자만 초대할 수 있습니다."},
        )
    if not db.get(Group, group_id):
        raise HTTPException(
            status_code=404, detail={"code": "GROUP_NOT_FOUND", "message": "그룹을 찾을 수 없습니다."}
        )

    email = body.email.strip().lower()

    # 가입 컬럼은 대소문자를 구분해 저장돼 있다. 비교는 양쪽 모두 소문자로.
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user:
        if db.get(GroupMembership, {"user_id": user.id, "group_id": group_id}):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "GROUP_INVITE_ALREADY_MEMBER",
                    "message": "이미 이 그룹에 있는 사람입니다.",
                },
            )
        # 이미 가입한 사람을 대기시킬 이유가 없다. 바로 넣되 기록은 남긴다.
        join_group(db, user.id, group_id)
        _upsert_invitation(db, group_id, email, current_user.id, accepted=True)
        db.commit()
        return {
            "success": True,
            "data": {
                "status": "joined",
                "email": email,
                "user": {"id": user.id, "email": user.email, "name": user.name},
            },
            "error": None,
        }

    existing = db.scalar(
        select(GroupInvitation).where(
            GroupInvitation.group_id == group_id, GroupInvitation.email == email
        )
    )
    if existing and existing.accepted_at is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "GROUP_INVITE_ALREADY_SENT",
                "message": "이미 초대해 둔 이메일입니다.",
            },
        )

    inv = _upsert_invitation(db, group_id, email, current_user.id, accepted=False)
    db.commit()
    return {
        "success": True,
        "data": {"status": "pending", "email": email, "invitation": _serialize_invitation(inv)},
        "error": None,
    }


@router.get("/groups/{group_id}/invitations")
def list_group_invitations(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """아직 가입하지 않은 대기 초대만. 합류한 사람은 멤버 목록에서 보인다."""
    if not db.get(Group, group_id):
        raise HTTPException(
            status_code=404, detail={"code": "GROUP_NOT_FOUND", "message": "그룹을 찾을 수 없습니다."}
        )
    if current_user.role != "admin" and not db.get(
        GroupMembership, {"user_id": current_user.id, "group_id": group_id}
    ):
        raise HTTPException(
            status_code=403,
            detail={"code": "GROUP_ACCESS_FORBIDDEN", "message": "이 그룹에 접근할 수 없습니다."},
        )

    invitations = db.scalars(
        select(GroupInvitation)
        .where(
            GroupInvitation.group_id == group_id,
            GroupInvitation.accepted_at.is_(None),
        )
        .order_by(GroupInvitation.created_at.desc())
    ).all()
    return {
        "success": True,
        "data": [_serialize_invitation(i) for i in invitations],
        "error": None,
    }


@router.delete("/groups/{group_id}/invitations/{invitation_id}")
def cancel_group_invitation(
    group_id: int,
    invitation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": "GROUP_INVITE_FORBIDDEN", "message": "관리자만 초대를 취소할 수 있습니다."},
        )
    inv = db.get(GroupInvitation, invitation_id)
    if not inv or inv.group_id != group_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "GROUP_INVITE_NOT_FOUND", "message": "초대를 찾을 수 없습니다."},
        )
    db.delete(inv)
    db.commit()
    return {"success": True, "data": {"deleted": True}, "error": None}


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
        # 그룹에서 빼면 방 접근은 이미 막히지만, 방 멤버 목록에는 계속 보인다. 같이 정리한다.
        room_ids = db.scalars(
            select(ChatRoom.id).where(ChatRoom.group_id == group_id)
        ).all()
        for room_member in db.scalars(
            select(ChatRoomMember).where(
                ChatRoomMember.room_id.in_(room_ids), ChatRoomMember.user_id == user_id
            )
        ).all():
            db.delete(room_member)
        db.commit()
    return {"success": True, "data": {"deleted": True}, "error": None}
