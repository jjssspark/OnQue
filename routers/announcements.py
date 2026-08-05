from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import get_current_user
from db import get_db
from models import Announcement, User

router = APIRouter(prefix="/api/v1", tags=["announcements"])


class AnnouncementCreateBody(BaseModel):
    title: str
    content: str


def _serialize(a: Announcement) -> dict:
    return {
        "id": a.id,
        "title": a.title,
        "content": a.content,
        "author_id": a.author_id,
        "created_at": a.created_at.isoformat(),
    }


@router.get("/announcements")
def list_announcements(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    items = db.scalars(select(Announcement).order_by(Announcement.created_at.desc())).all()
    return {"success": True, "data": [_serialize(a) for a in items], "error": None}


@router.post("/announcements")
def create_announcement(
    body: AnnouncementCreateBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": "ANNOUNCEMENT_CREATE_FORBIDDEN", "message": "관리자만 공지를 작성할 수 있습니다."},
        )
    announcement = Announcement(title=body.title, content=body.content, author_id=current_user.id)
    db.add(announcement)
    db.commit()
    db.refresh(announcement)
    return {"success": True, "data": _serialize(announcement), "error": None}
