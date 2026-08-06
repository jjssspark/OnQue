"""그룹 단위 권한 판정.

권한 검사가 라우터마다 흩어져 있으면 한 곳을 빠뜨렸을 때 조용히 뚫린다.
여기 모아 두면 판정 자체를 테스트할 수 있다.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import GroupMembership, User


def require_group_member(user: User, group_id: int, db: Session) -> GroupMembership:
    membership = db.get(GroupMembership, {"user_id": user.id, "group_id": group_id})
    if not membership:
        # 그룹이 아예 없는 경우도 여기로 온다. 404로 나누면 비멤버에게
        # 그룹 id의 존재 여부가 새어나간다.
        raise HTTPException(
            status_code=403,
            detail={"code": "GROUP_ACCESS_FORBIDDEN", "message": "해당 그룹에 소속되어 있지 않습니다."},
        )
    return membership


def require_group_admin(
    user: User,
    group_id: int,
    db: Session,
    *,
    code: str = "GROUP_ACCESS_FORBIDDEN",
    message: str = "이 팀의 관리자만 가능한 작업입니다.",
) -> GroupMembership:
    """엔드포인트마다 프론트가 분기하는 에러 코드가 다르므로 호출부가 지정한다."""
    membership = require_group_member(user, group_id, db)
    if membership.role != "admin":
        raise HTTPException(status_code=403, detail={"code": code, "message": message})
    return membership
