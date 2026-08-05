from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from auth import create_access_token, get_current_user, hash_password, verify_password
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
from routers.groups import get_user_groups, join_group

router = APIRouter(prefix="/api/v1", tags=["auth"])

DEFAULT_GROUP_NAME = "기본 그룹"


class SignupBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(min_length=1)


class LoginBody(BaseModel):
    email: str
    password: str


def _serialize_user(user: User) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role}


@router.post("/auth/signup")
def signup(body: SignupBody, db: Session = Depends(get_db)):
    existing = db.scalar(select(User).where(User.email == body.email))
    if existing:
        raise HTTPException(
            status_code=409,
            detail={"code": "USER_EMAIL_DUPLICATE", "message": "이미 가입된 이메일입니다."},
        )

    is_first_user = db.scalar(select(User).limit(1)) is None
    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        name=body.name,
        role="admin" if is_first_user else "member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # 첫 가입자는 관리자이자 워크스페이스의 시작점이다. 기본 그룹까지 만들어줘야
    # 로그인 직후 빈 화면을 마주하지 않는다.
    if is_first_user:
        group = Group(name=DEFAULT_GROUP_NAME, created_by=user.id)
        db.add(group)
        db.commit()
        db.refresh(group)
        db.add(GroupMembership(user_id=user.id, group_id=group.id))
        room = ChatRoom(
            group_id=group.id, name=DEFAULT_CHAT_ROOM_NAME, created_by=user.id
        )
        db.add(room)
        db.flush()
        db.add(ChatRoomMember(room_id=room.id, user_id=user.id))
        db.commit()

    # 가입 전에 받아둔 초대를 여기서 정산한다. 이 단계가 없으면 초대가 영영 닿지 않는다.
    pending = db.scalars(
        select(GroupInvitation).where(
            func.lower(GroupInvitation.email) == body.email.lower(),
            GroupInvitation.accepted_at.is_(None),
        )
    ).all()
    for invitation in pending:
        join_group(db, user.id, invitation.group_id)
        invitation.accepted_at = datetime.now(timezone.utc)
    if pending:
        db.commit()

    token = create_access_token(user.id)
    return {
        "success": True,
        "data": {"user": _serialize_user(user), "token": token},
        "error": None,
    }


@router.post("/auth/login")
def login(body: LoginBody, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_INVALID_CREDENTIALS", "message": "이메일 또는 비밀번호가 올바르지 않습니다."},
        )

    token = create_access_token(user.id)
    return {
        "success": True,
        "data": {"user": _serialize_user(user), "token": token},
        "error": None,
    }


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    groups = get_user_groups(current_user.id, db)

    return {
        "success": True,
        "data": {
            "user": _serialize_user(current_user),
            "groups": [{"id": g.id, "name": g.name} for g in groups],
        },
        "error": None,
    }
