from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
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
from permissions import require_group_admin, require_group_member

router = APIRouter(prefix="/api/v1", tags=["groups"])


def join_group(db: Session, user_id: int, group_id: int) -> None:
    """그룹에 합류시킨다. 커밋은 호출부가 한다.

    기본 방까지 넣어야 합류 직후 채팅 화면이 빈 목록이 아니다. 나머지 주제별
    방은 그 방에 있는 사람이 초대하게 둔다.
    """
    if db.get(GroupMembership, {"user_id": user_id, "group_id": group_id}):
        return

    db.add(GroupMembership(user_id=user_id, group_id=group_id, role="member"))
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


def get_user_groups_with_role(user_id: int, db: Session) -> list[dict]:
    """/me 응답용. 그룹 안에서의 역할까지 함께 내려줘야 프론트가 관리자 UI를 분기한다."""
    memberships = db.scalars(
        select(GroupMembership).where(GroupMembership.user_id == user_id)
    ).all()
    if not memberships:
        return []
    groups_by_id = {
        g.id: g
        for g in db.scalars(
            select(Group).where(Group.id.in_([m.group_id for m in memberships]))
        ).all()
    }
    return [
        {"id": m.group_id, "name": groups_by_id[m.group_id].name, "role": m.role}
        for m in memberships
    ]


class GroupCreateBody(BaseModel):
    name: str = Field(min_length=1)


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
    """인증된 사용자면 누구나 팀을 만들 수 있고, 만든 사람이 그 팀의 관리자가 된다.

    그룹·멤버십·기본 방을 한 트랜잭션에서 만든다. 나눠 커밋하면 중간에
    실패했을 때 멤버십 없는 고아 그룹이 남고, 만든 사람조차 접근할 수 없다.
    """
    group = Group(name=body.name, created_by=current_user.id)
    db.add(group)
    db.flush()
    db.add(GroupMembership(user_id=current_user.id, group_id=group.id, role="admin"))
    room = ChatRoom(
        group_id=group.id, name=DEFAULT_CHAT_ROOM_NAME, created_by=current_user.id
    )
    db.add(room)
    db.flush()
    db.add(ChatRoomMember(room_id=room.id, user_id=current_user.id))
    db.commit()
    db.refresh(group)
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
    require_group_member(current_user, group_id, db)

    memberships = db.scalars(
        select(GroupMembership).where(GroupMembership.group_id == group_id)
    ).all()
    role_by_user = {m.user_id: m.role for m in memberships}
    users = (
        db.scalars(select(User).where(User.id.in_(role_by_user))).all()
        if role_by_user
        else []
    )
    return {
        "success": True,
        "data": [
            {"id": u.id, "email": u.email, "name": u.name, "role": role_by_user[u.id]}
            for u in users
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
    require_group_admin(
        current_user, group_id, db,
        code="GROUP_MEMBER_ADD_FORBIDDEN", message="관리자만 가능한 작업입니다.",
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
    """이메일로 초대한다. 누구든 수락해야 들어간다 — 가입 여부와 무관하게 대기 상태로 남는다."""
    require_group_admin(
        current_user, group_id, db,
        code="GROUP_INVITE_FORBIDDEN", message="관리자만 초대할 수 있습니다.",
    )

    email = body.email.strip().lower()

    # 이미 우리 팀 멤버인지 확인한다. 관리자가 GET /groups/{id}/members로
    # 이미 볼 수 있는 정보라 이 409는 새로 새는 것이 없다.
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user and db.get(GroupMembership, {"user_id": user.id, "group_id": group_id}):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "GROUP_INVITE_ALREADY_MEMBER",
                "message": "이미 이 그룹에 있는 사람입니다.",
            },
        )

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

    # 가입자든 미가입자든 여기 하나로 모인다. 응답이 갈리면 임의 이메일의
    # 가입 여부를 알아낼 수 있다.
    _upsert_invitation(db, group_id, email, current_user.id, accepted=False)
    db.commit()
    return {
        "success": True,
        "data": {"status": "invited", "email": email},
        "error": None,
    }


@router.get("/groups/{group_id}/invitations")
def list_group_invitations(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """아직 가입하지 않은 대기 초대만. 합류한 사람은 멤버 목록에서 보인다."""
    require_group_member(current_user, group_id, db)

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
    require_group_admin(
        current_user, group_id, db,
        code="GROUP_INVITE_FORBIDDEN", message="관리자만 초대를 취소할 수 있습니다.",
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
    require_group_admin(
        current_user, group_id, db,
        code="GROUP_MEMBER_ADD_FORBIDDEN", message="관리자만 가능한 작업입니다.",
    )
    membership = db.get(GroupMembership, {"user_id": user_id, "group_id": group_id})
    if membership and membership.role == "admin":
        admin_count = db.scalar(
            select(func.count())
            .select_from(GroupMembership)
            .where(GroupMembership.group_id == group_id, GroupMembership.role == "admin")
        )
        if admin_count <= 1:
            # 전역 admin이 없어졌으므로 관리자가 0명이 되면 아무도 초대할 수
            # 없고 밖에서 고쳐줄 사람도 없다.
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "GROUP_LAST_ADMIN",
                    "message": "팀의 마지막 관리자는 내보낼 수 없습니다.",
                },
            )
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
