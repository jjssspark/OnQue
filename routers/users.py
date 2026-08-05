from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import get_current_user
from db import get_db
from models import User

router = APIRouter(prefix="/api/v1", tags=["users"])


def serialize_user(user: User) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role}


@router.get("/users")
def list_users(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    # 그룹에 초대할 대상을 고르려면 관리자가 사용자 목록을 볼 수 있어야 한다.
    # 일반 멤버에게는 다른 직원의 이메일까지 노출할 이유가 없어 관리자로 제한한다.
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": "USER_LIST_FORBIDDEN", "message": "관리자만 가능한 작업입니다."},
        )
    users = db.scalars(select(User).order_by(User.created_at)).all()
    return {"success": True, "data": [serialize_user(u) for u in users], "error": None}
