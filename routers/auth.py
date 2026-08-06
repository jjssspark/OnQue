from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from auth import create_access_token, get_current_user, hash_password, verify_password
from db import get_db
from models import GroupInvitation, User
from routers.groups import get_user_groups_with_role, join_group

router = APIRouter(prefix="/api/v1", tags=["auth"])


class SignupBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(min_length=1)


class LoginBody(BaseModel):
    email: str
    password: str


def _serialize_user(user: User) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name}


@router.post("/auth/signup")
def signup(body: SignupBody, db: Session = Depends(get_db)):
    existing = db.scalar(select(User).where(User.email == body.email))
    if existing:
        raise HTTPException(
            status_code=409,
            detail={"code": "USER_EMAIL_DUPLICATE", "message": "이미 가입된 이메일입니다."},
        )

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        name=body.name,
        role="member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

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
    return {
        "success": True,
        "data": {
            "user": _serialize_user(current_user),
            "groups": get_user_groups_with_role(current_user.id, db),
        },
        "error": None,
    }
