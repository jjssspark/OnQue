from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from auth import create_access_token, get_current_user, hash_password, verify_password
from db import get_db
from models import Group, GroupInvitation, User
from routers.groups import get_user_groups_with_role, join_group

router = APIRouter(prefix="/api/v1", tags=["auth"])


class SignupBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(min_length=1)


class LoginBody(BaseModel):
    email: str
    password: str


class ProfileUpdateBody(BaseModel):
    name: str = Field(min_length=1)


class PasswordChangeBody(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


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
            "user": {
                **_serialize_user(current_user),
                "created_at": current_user.created_at.isoformat(),
            },
            "groups": get_user_groups_with_role(current_user.id, db),
        },
        "error": None,
    }


@router.patch("/me")
def update_me(
    body: ProfileUpdateBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.name = body.name
    db.commit()
    db.refresh(current_user)
    return {"success": True, "data": _serialize_user(current_user), "error": None}


@router.post("/me/password")
def change_my_password(
    body: PasswordChangeBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """현재 비밀번호를 반드시 확인한다. 토큰만으로 바꿀 수 있으면
    탈취된 토큰이 그대로 계정 탈취가 된다."""
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=400,
            detail={"code": "USER_PASSWORD_INVALID", "message": "현재 비밀번호가 올바르지 않습니다."},
        )
    current_user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"success": True, "data": {"changed": True}, "error": None}


def _pending_invitation_for(db: Session, user: User, invitation_id: int) -> GroupInvitation:
    """내 이메일로 온 대기 초대만 돌려준다.

    남의 초대나 이미 수락된 초대는 404다. 403으로 나누면 초대 id의 존재
    여부가 새어나간다 — permissions.py가 그룹에서 쓴 것과 같은 원칙이다.
    """
    inv = db.get(GroupInvitation, invitation_id)
    if (
        inv is None
        or inv.accepted_at is not None
        or inv.email.lower() != user.email.lower()
    ):
        raise HTTPException(
            status_code=404,
            detail={"code": "INVITATION_NOT_FOUND", "message": "초대를 찾을 수 없습니다."},
        )
    return inv


@router.get("/me/invitations")
def list_my_invitations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(
            GroupInvitation.id,
            GroupInvitation.group_id,
            Group.name,
            User.name,
            GroupInvitation.created_at,
        )
        .join(Group, Group.id == GroupInvitation.group_id)
        .join(User, User.id == GroupInvitation.invited_by)
        .where(
            func.lower(GroupInvitation.email) == current_user.email.lower(),
            GroupInvitation.accepted_at.is_(None),
        )
        .order_by(GroupInvitation.created_at.desc())
    ).all()

    return {
        "success": True,
        "data": [
            {
                "id": inv_id,
                "group_id": group_id,
                "group_name": group_name,
                "invited_by_name": inviter_name,
                "created_at": created_at.isoformat(),
            }
            for inv_id, group_id, group_name, inviter_name, created_at in rows
        ],
        "error": None,
    }


@router.post("/me/invitations/{invitation_id}/accept")
def accept_my_invitation(
    invitation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    inv = _pending_invitation_for(db, current_user, invitation_id)
    join_group(db, current_user.id, inv.group_id)
    inv.accepted_at = datetime.now(timezone.utc)
    db.commit()
    return {"success": True, "data": {"group_id": inv.group_id}, "error": None}


@router.delete("/me/invitations/{invitation_id}")
def decline_my_invitation(
    invitation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """거절은 행을 지운다. declined_at 컬럼을 두면 Alembic 없는 이 프로젝트에서
    마이그레이션 배포가 한 번 더 필요해지는데, 사내 규모에서 거절 이력의
    값이 그 비용보다 작다. 관리자가 다시 초대하면 새 행이 생긴다."""
    inv = _pending_invitation_for(db, current_user, invitation_id)
    db.delete(inv)
    db.commit()
    return {"success": True, "data": {"declined": True}, "error": None}
