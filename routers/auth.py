from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import create_access_token, get_current_user, hash_password, verify_password
from db import get_db
from models import Group, GroupMembership, User

router = APIRouter(prefix="/api/v1", tags=["auth"])


class SignupBody(BaseModel):
    email: str
    password: str
    name: str


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
    memberships = db.scalars(
        select(GroupMembership).where(GroupMembership.user_id == current_user.id)
    ).all()
    group_ids = [m.group_id for m in memberships]
    groups = db.scalars(select(Group).where(Group.id.in_(group_ids))).all() if group_ids else []

    return {
        "success": True,
        "data": {
            "user": _serialize_user(current_user),
            "groups": [{"id": g.id, "name": g.name} for g in groups],
        },
        "error": None,
    }
