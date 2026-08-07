from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from auth import get_current_user
from db import get_db
from models import Announcement, User
from permissions import require_group_admin, require_group_member

router = APIRouter(prefix="/api/v1", tags=["announcements"])


class AnnouncementCreateBody(BaseModel):
    group_id: int
    title: str
    content: str


def _serialize(a: Announcement) -> dict:
    return {
        "id": a.id,
        "group_id": a.group_id,
        "title": a.title,
        "content": a.content,
        "author_id": a.author_id,
        "created_at": a.created_at.isoformat(),
    }


@router.get("/announcements")
def list_announcements(
    group_id: int,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_group_member(current_user, group_id, db)
    total = db.scalar(
        select(func.count()).select_from(Announcement).where(Announcement.group_id == group_id)
    )
    items = db.scalars(
        select(Announcement)
        .where(Announcement.group_id == group_id)
        .order_by(Announcement.created_at.desc())
        .limit(limit)
    ).all()
    return {
        "success": True,
        "data": [_serialize(a) for a in items],
        "error": None,
        "meta": {"total": total, "limit": limit, "hasNext": total > len(items)},
    }


@router.post("/announcements")
def create_announcement(
    body: AnnouncementCreateBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_group_admin(
        current_user, body.group_id, db,
        code="ANNOUNCEMENT_CREATE_FORBIDDEN",
        message="팀 관리자만 공지를 작성할 수 있습니다.",
    )
    announcement = Announcement(
        group_id=body.group_id,
        title=body.title,
        content=body.content,
        author_id=current_user.id,
    )
    db.add(announcement)
    db.commit()
    db.refresh(announcement)
    return {"success": True, "data": _serialize(announcement), "error": None}
