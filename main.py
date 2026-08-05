import os
from datetime import date, datetime

from fastapi import Depends, FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

import gemini_service
from db import Base, engine, get_db
from routers.auth import router as auth_router
from routers.groups import router as groups_router
from routers.announcements import router as announcements_router
from auth import get_current_user
from models import ChatMessage, Document, GroupMembership, Schedule, Todo, User

Base.metadata.create_all(bind=engine)

app = FastAPI()

from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException as FastAPIHTTPException


@app.exception_handler(FastAPIHTTPException)
async def http_exception_handler(request, exc: FastAPIHTTPException):
    if isinstance(exc.detail, dict):
        error = exc.detail
    else:
        error = {"code": "INTERNAL_ERROR", "message": str(exc.detail)}
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "data": None, "error": error},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 개발 중이라 전체 허용, 나중엔 도메인 제한 추천
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(groups_router)
app.include_router(announcements_router)


@app.get("/")
def health_check():
    return {"status": "ok", "message": "OnQue FastAPI with Gemini"}


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _hint_matches(text: str, hint: str) -> bool:
    a, b = text.strip().lower(), hint.strip().lower()
    if not a or not b:
        return False
    return a in b or b in a


def _require_group_member(user: User, group_id: int, db: Session) -> None:
    membership = db.get(GroupMembership, {"user_id": user.id, "group_id": group_id})
    if not membership:
        raise HTTPException(
            status_code=403,
            detail={"code": "GROUP_ACCESS_FORBIDDEN", "message": "해당 그룹에 소속되어 있지 않습니다."},
        )


# ── 통화/문서 요약 ──────────────────────────────────────────


@app.post("/summarize-call")
async def summarize_call(
    group_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """통화 녹음 파일(mp3, m4a, wav 등)을 받아 Gemini로 요약하고 이력에 저장한다."""
    _require_group_member(current_user, group_id, db)

    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(
            status_code=400,
            detail=f"오디오 파일만 업로드 가능합니다. (현재 content_type: {file.content_type})",
        )

    summary_text = await gemini_service.summarize_upload(file, gemini_service.CALL_SUMMARY_PROMPT)

    doc = Document(
        group_id=group_id,
        source_type="call",
        category="통화",
        filename=file.filename,
        summary=summary_text,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return {
        "id": doc.id,
        "filename": doc.filename,
        "summary": doc.summary,
        "category": doc.category,
    }


ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".txt", ".md"}


@app.post("/summarize-document")
async def summarize_document(
    group_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """문서/회의록 파일(pdf, txt, md)을 받아 Gemini로 요약·분류하고 이력에 저장한다."""
    _require_group_member(current_user, group_id, db)

    suffix = os.path.splitext(file.filename or "")[1].lower()
    if suffix not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"pdf, txt, md 파일만 업로드 가능합니다. (현재 확장자: {suffix or '없음'})",
        )

    summary_text = await gemini_service.summarize_upload(
        file, gemini_service.DOCUMENT_SUMMARY_PROMPT
    )
    category = gemini_service.classify_document_category(summary_text)

    doc = Document(
        group_id=group_id,
        source_type="document",
        category=category,
        filename=file.filename,
        summary=summary_text,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return {
        "id": doc.id,
        "filename": doc.filename,
        "summary": doc.summary,
        "category": doc.category,
    }


def _serialize_document(doc: Document) -> dict:
    return {
        "id": doc.id,
        "source_type": doc.source_type,
        "category": doc.category,
        "filename": doc.filename,
        "summary": doc.summary,
        "created_at": doc.created_at.isoformat(),
    }


@app.get("/documents")
def list_documents(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_group_member(current_user, group_id, db)
    docs = db.scalars(
        select(Document)
        .where((Document.group_id == group_id) | (Document.is_template.is_(True)))
        .order_by(Document.created_at.desc())
        .limit(100)
    ).all()
    return [_serialize_document(d) for d in docs]


@app.delete("/documents/{document_id}")
def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    if doc.group_id is not None:
        _require_group_member(current_user, doc.group_id, db)
    db.delete(doc)
    db.commit()
    return {"deleted": True}


# ── 할 일 / 일정 ──────────────────────────────────────────


class TodoUpdate(BaseModel):
    is_done: bool | None = None
    content: str | None = None
    due_date: str | None = None


def _serialize_todo(todo: Todo) -> dict:
    return {
        "id": todo.id,
        "content": todo.content,
        "due_date": todo.due_date.isoformat() if todo.due_date else None,
        "is_done": todo.is_done,
        "created_at": todo.created_at.isoformat(),
    }


@app.get("/todos")
def list_todos(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_group_member(current_user, group_id, db)
    todos = db.scalars(
        select(Todo)
        .where(Todo.group_id == group_id)
        .order_by(Todo.is_done.asc(), Todo.created_at.desc())
    ).all()
    return [_serialize_todo(t) for t in todos]


@app.patch("/todos/{todo_id}")
def update_todo(
    todo_id: int,
    body: TodoUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    todo = db.get(Todo, todo_id)
    if not todo:
        raise HTTPException(status_code=404, detail="할 일을 찾을 수 없습니다.")
    _require_group_member(current_user, todo.group_id, db)
    if body.is_done is not None:
        todo.is_done = body.is_done
    if body.content is not None:
        todo.content = body.content
    if body.due_date is not None:
        todo.due_date = _parse_date(body.due_date)
    db.commit()
    db.refresh(todo)
    return _serialize_todo(todo)


@app.delete("/todos/{todo_id}")
def delete_todo(
    todo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    todo = db.get(Todo, todo_id)
    if not todo:
        raise HTTPException(status_code=404, detail="할 일을 찾을 수 없습니다.")
    _require_group_member(current_user, todo.group_id, db)
    db.delete(todo)
    db.commit()
    return {"deleted": True}


class ScheduleUpdate(BaseModel):
    title: str | None = None
    scheduled_date: str | None = None


class ScheduleCreate(BaseModel):
    title: str
    scheduled_date: str
    group_id: int | None = None


def _serialize_schedule(schedule: Schedule) -> dict:
    return {
        "id": schedule.id,
        "title": schedule.title,
        "scheduled_date": schedule.scheduled_date.isoformat(),
        "created_at": schedule.created_at.isoformat(),
    }


@app.post("/schedules")
def create_schedule(
    body: ScheduleCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.group_id is not None:
        _require_group_member(current_user, body.group_id, db)
    elif current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": "SCHEDULE_EDIT_FORBIDDEN", "message": "전사 일정은 관리자만 등록할 수 있습니다."},
        )
    scheduled = _parse_date(body.scheduled_date)
    if not scheduled:
        raise HTTPException(status_code=400, detail="scheduled_date 형식이 올바르지 않습니다. (YYYY-MM-DD)")
    schedule = Schedule(group_id=body.group_id, title=body.title, scheduled_date=scheduled)
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return _serialize_schedule(schedule)


@app.get("/schedules")
def list_schedules(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_group_member(current_user, group_id, db)
    schedules = db.scalars(
        select(Schedule)
        .where((Schedule.group_id == group_id) | (Schedule.group_id.is_(None)))
        .order_by(Schedule.scheduled_date.asc())
    ).all()
    return [_serialize_schedule(s) for s in schedules]


@app.patch("/schedules/{schedule_id}")
def update_schedule(
    schedule_id: int,
    body: ScheduleUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    schedule = db.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다.")
    if schedule.group_id is not None:
        _require_group_member(current_user, schedule.group_id, db)
    elif current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": "SCHEDULE_EDIT_FORBIDDEN", "message": "전사 일정은 관리자만 수정할 수 있습니다."},
        )
    if body.title is not None:
        schedule.title = body.title
    if body.scheduled_date is not None:
        parsed = _parse_date(body.scheduled_date)
        if parsed:
            schedule.scheduled_date = parsed
    db.commit()
    db.refresh(schedule)
    return _serialize_schedule(schedule)


@app.delete("/schedules/{schedule_id}")
def delete_schedule(
    schedule_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    schedule = db.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다.")
    if schedule.group_id is not None:
        _require_group_member(current_user, schedule.group_id, db)
    elif current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": "SCHEDULE_EDIT_FORBIDDEN", "message": "전사 일정은 관리자만 수정할 수 있습니다."},
        )
    db.delete(schedule)
    db.commit()
    return {"deleted": True}


# ── 팀 채팅 (@비서) ──────────────────────────────────────────


class ChatMessageCreate(BaseModel):
    sender: str
    content: str


def _serialize_message(message: ChatMessage) -> dict:
    return {
        "id": message.id,
        "sender": message.sender,
        "content": message.content,
        "is_bot": message.is_bot,
        "created_at": message.created_at.isoformat(),
    }


@app.get("/chat/messages")
def list_chat_messages(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_group_member(current_user, group_id, db)
    messages = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.group_id == group_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(50)
    ).all()
    return [_serialize_message(m) for m in reversed(messages)]


def _apply_extracted_actions(db: Session, group_id: int, actions: dict) -> None:
    for item in actions.get("add_todos", []):
        content = (item.get("content") or "").strip()
        if not content:
            continue
        db.add(
            Todo(
                group_id=group_id,
                content=content,
                due_date=_parse_date(item.get("due_date", "")),
            )
        )

    if actions.get("complete_todo_hints") or actions.get("delete_todo_hints"):
        open_todos = db.scalars(
            select(Todo).where(Todo.group_id == group_id, Todo.is_done.is_(False))
        ).all()
        for hint in actions.get("complete_todo_hints", []):
            for todo in open_todos:
                if not todo.is_done and _hint_matches(todo.content, hint):
                    todo.is_done = True
                    break

        all_todos = db.scalars(select(Todo).where(Todo.group_id == group_id)).all()
        for hint in actions.get("delete_todo_hints", []):
            for todo in all_todos:
                if _hint_matches(todo.content, hint):
                    db.delete(todo)
                    break

    for item in actions.get("add_schedules", []):
        title = (item.get("title") or "").strip()
        scheduled = _parse_date(item.get("date", ""))
        if not title or not scheduled:
            continue
        db.add(Schedule(group_id=group_id, title=title, scheduled_date=scheduled))

    if actions.get("delete_schedule_hints"):
        all_schedules = db.scalars(select(Schedule).where(Schedule.group_id == group_id)).all()
        for hint in actions.get("delete_schedule_hints", []):
            for schedule in all_schedules:
                if _hint_matches(schedule.title, hint):
                    db.delete(schedule)
                    break


@app.post("/chat/messages")
def create_chat_message(
    group_id: int,
    body: ChatMessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_group_member(current_user, group_id, db)
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="메시지 내용이 비어 있습니다.")

    user_message = ChatMessage(group_id=group_id, sender=body.sender, content=content, is_bot=False)
    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    actions = gemini_service.extract_chat_actions(content)
    _apply_extracted_actions(db, group_id, actions)
    db.commit()

    bot_message = None
    if "@비서" in content:
        recent = db.scalars(
            select(ChatMessage)
            .where(ChatMessage.group_id == group_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(10)
        ).all()
        history = [
            {"sender": m.sender, "content": m.content} for m in reversed(recent)
        ]
        reply_text = gemini_service.generate_bot_reply(history, content)
        bot_message = ChatMessage(group_id=group_id, sender="비서", content=reply_text, is_bot=True)
        db.add(bot_message)
        db.commit()
        db.refresh(bot_message)

    todos = db.scalars(
        select(Todo)
        .where(Todo.group_id == group_id)
        .order_by(Todo.is_done.asc(), Todo.created_at.desc())
    ).all()
    schedules = db.scalars(
        select(Schedule)
        .where((Schedule.group_id == group_id) | (Schedule.group_id.is_(None)))
        .order_by(Schedule.scheduled_date.asc())
    ).all()

    return {
        "message": _serialize_message(user_message),
        "bot_message": _serialize_message(bot_message) if bot_message else None,
        "todos": [_serialize_todo(t) for t in todos],
        "schedules": [_serialize_schedule(s) for s in schedules],
    }
