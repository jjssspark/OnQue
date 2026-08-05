import json
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
from routers.users import router as users_router
from routers.announcements import router as announcements_router
from auth import get_current_user
from models import (
    ChatMessage,
    ChatRoom,
    Document,
    GroupMembership,
    Schedule,
    Todo,
    User,
)

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
app.include_router(users_router)


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


def _create_todos_from_actions(
    db: Session, group_id: int, action_items: list[dict]
) -> list[Todo]:
    """요약에서 뽑은 액션 아이템을 할 일로 등록하고 생성된 항목을 돌려준다."""

    created: list[Todo] = []
    for item in action_items:
        content = (item.get("content") or "").strip()
        if not content:
            continue
        todo = Todo(
            group_id=group_id,
            content=content,
            due_date=_parse_date(item.get("due_date") or ""),
        )
        db.add(todo)
        created.append(todo)
    return created


async def _summarize_and_store(
    db: Session,
    group_id: int,
    file: UploadFile,
    prompt: str,
    source_type: str,
    auto_todo: bool,
    category: str | None = None,
) -> dict:
    """요약 → 저장 → (선택) 할 일 등록까지의 공통 흐름."""

    structured, summary_text = await gemini_service.summarize_upload(file, prompt)

    doc = Document(
        group_id=group_id,
        source_type=source_type,
        category=category or gemini_service.classify_document_category(summary_text),
        filename=file.filename,
        summary=summary_text,
        summary_json=json.dumps(structured, ensure_ascii=False) if structured else None,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    created_todos: list[Todo] = []
    if auto_todo and structured:
        created_todos = _create_todos_from_actions(db, group_id, structured["action_items"])
        db.commit()
        for todo in created_todos:
            db.refresh(todo)

    return {
        "id": doc.id,
        "filename": doc.filename,
        "summary": doc.summary,
        "category": doc.category,
        "structured": structured,
        "created_todos": [_serialize_todo(t) for t in created_todos],
    }


@app.post("/summarize-call")
async def summarize_call(
    group_id: int,
    auto_todo: bool = False,
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

    return await _summarize_and_store(
        db,
        group_id,
        file,
        gemini_service.CALL_SUMMARY_PROMPT,
        source_type="call",
        auto_todo=auto_todo,
        category="통화",
    )


ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".txt", ".md"}


@app.post("/summarize-document")
async def summarize_document(
    group_id: int,
    auto_todo: bool = False,
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

    return await _summarize_and_store(
        db,
        group_id,
        file,
        gemini_service.DOCUMENT_SUMMARY_PROMPT,
        source_type="document",
        auto_todo=auto_todo,
    )


def _parse_summary_json(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def _serialize_document(doc: Document) -> dict:
    return {
        "id": doc.id,
        "source_type": doc.source_type,
        "category": doc.category,
        "filename": doc.filename,
        "summary": doc.summary,
        "structured": _parse_summary_json(doc.summary_json),
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
        .where(
            (Document.group_id == group_id)
            | ((Document.is_template.is_(True)) & (Document.group_id.is_(None)))
        )
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
    elif current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": "DOCUMENT_DELETE_FORBIDDEN", "message": "전사 공유 문서는 관리자만 삭제할 수 있습니다."},
        )
    db.delete(doc)
    db.commit()
    return {"deleted": True}


# ── 할 일 / 일정 ──────────────────────────────────────────


class TodoUpdate(BaseModel):
    is_done: bool | None = None
    content: str | None = None
    due_date: str | None = None


class TodoCreate(BaseModel):
    group_id: int
    content: str
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


@app.post("/todos")
def create_todo(
    body: TodoCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """요약 리포트에서 액션 아이템을 골라 등록할 때 쓰는 수동 생성 엔드포인트."""
    _require_group_member(current_user, body.group_id, db)

    content = body.content.strip()
    if not content:
        raise HTTPException(
            status_code=400,
            detail={"code": "TODO_CONTENT_REQUIRED", "message": "할 일 내용이 비어 있습니다."},
        )

    todo = Todo(
        group_id=body.group_id,
        content=content,
        due_date=_parse_date(body.due_date or ""),
    )
    db.add(todo)
    db.commit()
    db.refresh(todo)
    return _serialize_todo(todo)


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
        raise HTTPException(
            status_code=400,
            detail={"code": "SCHEDULE_DATE_INVALID", "message": "scheduled_date 형식이 올바르지 않습니다. (YYYY-MM-DD)"},
        )
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


class ChatRoomCreate(BaseModel):
    group_id: int
    name: str


def _serialize_message(message: ChatMessage) -> dict:
    return {
        "id": message.id,
        "room_id": message.room_id,
        "sender": message.sender,
        "content": message.content,
        "is_bot": message.is_bot,
        "created_at": message.created_at.isoformat(),
    }


BOT_SENDER = "비서"

# 명령어와 안내 문구. /help 응답이 이 목록에서 그대로 만들어지므로 한 곳만 고치면 된다.
CHAT_COMMANDS = {
    "/help": "AI 비서를 이 방으로 부릅니다",
    "/exit": "AI 비서를 내보냅니다",
    "/요약": "최근 대화를 요약합니다",
    "/문서": "최근 대화로 회의록 초안을 만듭니다 (예: /문서 8월 첫째주 회의록)",
    "/할일": "할 일을 등록합니다 (예: /할일 견적서 8월 12일까지)",
    "/질문": "AI에게 한 번만 묻습니다 (예: /질문 A안과 B안 차이가 뭐야)",
}

HELP_TEXT = "AI 비서가 들어왔습니다. 이제 이 방의 대화를 함께 봅니다.\n\n" + "\n".join(
    f"{cmd}  —  {desc}" for cmd, desc in CHAT_COMMANDS.items()
)

EXIT_TEXT = "AI 비서가 나갔습니다. 이제 사람들끼리의 대화로 돌아갑니다. 다시 부르려면 /help 를 입력하세요."


def _serialize_room(room: ChatRoom, last: ChatMessage | None) -> dict:
    return {
        "id": room.id,
        "group_id": room.group_id,
        "name": room.name,
        "ai_mode": room.ai_mode,
        "created_at": room.created_at.isoformat(),
        "last_message": _serialize_message(last) if last else None,
    }


def _require_room_access(user: User, room_id: int, db: Session) -> ChatRoom:
    """방을 찾고 그룹 멤버십까지 확인한 뒤 방을 돌려준다."""
    room = db.get(ChatRoom, room_id)
    if not room:
        raise HTTPException(
            status_code=404,
            detail={"code": "CHAT_ROOM_NOT_FOUND", "message": "채팅방을 찾을 수 없습니다."},
        )
    _require_group_member(user, room.group_id, db)
    return room


@app.get("/chat/rooms")
def list_chat_rooms(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """목록 화면에 필요한 마지막 메시지 미리보기까지 함께 내려준다."""
    _require_group_member(current_user, group_id, db)

    rooms = db.scalars(
        select(ChatRoom).where(ChatRoom.group_id == group_id).order_by(ChatRoom.created_at.asc())
    ).all()

    result = []
    for room in rooms:
        last = db.scalars(
            select(ChatMessage)
            .where(ChatMessage.room_id == room.id)
            .order_by(ChatMessage.created_at.desc())
            .limit(1)
        ).first()
        result.append(_serialize_room(room, last))
    return result


@app.post("/chat/rooms")
def create_chat_room(
    body: ChatRoomCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_group_member(current_user, body.group_id, db)

    name = body.name.strip()
    if not name:
        raise HTTPException(
            status_code=400,
            detail={"code": "CHAT_ROOM_NAME_REQUIRED", "message": "채팅방 이름이 비어 있습니다."},
        )

    room = ChatRoom(group_id=body.group_id, name=name, created_by=current_user.id)
    db.add(room)
    db.commit()
    db.refresh(room)
    return _serialize_room(room, None)


@app.delete("/chat/rooms/{room_id}")
def delete_chat_room(
    room_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room = _require_room_access(current_user, room_id, db)
    if room.created_by != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "CHAT_ROOM_DELETE_FORBIDDEN",
                "message": "방을 만든 사람이나 관리자만 삭제할 수 있습니다.",
            },
        )

    # 메시지를 먼저 지워야 외래키 제약에 걸리지 않는다.
    for message in db.scalars(select(ChatMessage).where(ChatMessage.room_id == room_id)).all():
        db.delete(message)
    db.delete(room)
    db.commit()
    return {"deleted": True}


@app.get("/chat/messages")
def list_chat_messages(
    room_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_room_access(current_user, room_id, db)
    messages = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.room_id == room_id)
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


def _post_bot_message(db: Session, room_id: int, text: str) -> ChatMessage:
    message = ChatMessage(room_id=room_id, sender=BOT_SENDER, content=text, is_bot=True)
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def _recent_history(db: Session, room_id: int, limit: int = 20) -> list[dict]:
    recent = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.room_id == room_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    ).all()
    return [{"sender": m.sender, "content": m.content} for m in reversed(recent)]


def _handle_command(
    db: Session, room: ChatRoom, command: str, argument: str
) -> ChatMessage | None:
    """명령어를 처리하고 봇 응답 메시지를 돌려준다."""

    if command == "/help":
        room.ai_mode = True
        db.commit()
        return _post_bot_message(db, room.id, HELP_TEXT)

    if command == "/exit":
        room.ai_mode = False
        db.commit()
        return _post_bot_message(db, room.id, EXIT_TEXT)

    if command == "/요약":
        summary = gemini_service.summarize_conversation(_recent_history(db, room.id))
        return _post_bot_message(db, room.id, summary)

    if command == "/문서":
        title = argument or "채팅 회의록"
        structured = gemini_service.draft_document_from_conversation(
            _recent_history(db, room.id), title
        )
        if not structured:
            return _post_bot_message(
                db, room.id, "문서로 만들 대화가 부족합니다. 대화가 쌓인 뒤 다시 시도해주세요."
            )

        summary_text = gemini_service.render_summary_text(structured)
        doc = Document(
            group_id=room.group_id,
            source_type="document",
            category=gemini_service.classify_document_category(summary_text),
            filename=title,
            summary=summary_text,
            summary_json=json.dumps(structured, ensure_ascii=False),
        )
        db.add(doc)
        db.commit()
        return _post_bot_message(
            db,
            room.id,
            f"'{title}' 문서를 만들어 이력에 저장했습니다.\n\n{structured['headline']}",
        )

    if command == "/할일":
        if not argument:
            return _post_bot_message(
                db, room.id, "등록할 내용을 함께 적어주세요. 예: /할일 견적서 8월 12일까지"
            )
        # 날짜 표현을 그대로 살리려고 추출기를 재사용한다. "8월 12일까지" -> 2026-08-12
        actions = gemini_service.extract_chat_actions(argument)
        created = _create_todos_from_actions(db, room.group_id, actions.get("add_todos", []))
        if not created:
            created = [Todo(group_id=room.group_id, content=argument)]
            db.add(created[0])
        db.commit()
        names = "\n".join(f"- {t.content}" for t in created)
        return _post_bot_message(db, room.id, f"할 일에 등록했습니다.\n{names}")

    if command == "/질문":
        if not argument:
            return _post_bot_message(db, room.id, "질문 내용을 함께 적어주세요. 예: /질문 A안과 B안 차이가 뭐야")
        reply = gemini_service.generate_bot_reply(_recent_history(db, room.id), argument)
        return _post_bot_message(db, room.id, reply)

    known = " ".join(CHAT_COMMANDS)
    return _post_bot_message(
        db, room.id, f"'{command}'는 모르는 명령입니다.\n사용 가능: {known}"
    )


@app.post("/chat/messages")
def create_chat_message(
    room_id: int,
    body: ChatMessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room = _require_room_access(current_user, room_id, db)
    group_id = room.group_id
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="메시지 내용이 비어 있습니다.")

    user_message = ChatMessage(room_id=room_id, sender=body.sender, content=content, is_bot=False)
    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    bot_message = None
    if content.startswith("/"):
        command, _, argument = content.partition(" ")
        bot_message = _handle_command(db, room, command.strip(), argument.strip())
    elif room.ai_mode:
        # AI가 방에 들어와 있을 때만 대화를 읽는다. 평소엔 Gemini를 호출하지 않는다.
        actions = gemini_service.extract_chat_actions(content)
        _apply_extracted_actions(db, group_id, actions)
        db.commit()
        reply_text = gemini_service.generate_bot_reply(_recent_history(db, room_id), content)
        bot_message = _post_bot_message(db, room_id, reply_text)

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
        "ai_mode": room.ai_mode,
        "todos": [_serialize_todo(t) for t in todos],
        "schedules": [_serialize_schedule(s) for s in schedules],
    }
