import json
import logging
import os
from datetime import date, datetime
from typing import NoReturn

from fastapi import Depends, FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import call_budget
import commitment_service
import gemini_service
from db import Base, engine, get_db
from routers.auth import router as auth_router
from routers.groups import router as groups_router
from routers.announcements import router as announcements_router
from routers.commitments import router as commitments_router
from routers.assistant import router as assistant_router
from auth import get_current_user
from permissions import require_group_admin, require_group_member
from models import (
    ChatMessage,
    ChatRoom,
    ChatRoomMember,
    Commitment,
    Document,
    GroupMembership,
    Schedule,
    Todo,
    User,
)

# uvicorn 기본 설정은 자기 로거만 다루고 루트에는 핸들러를 두지 않는다. 그래서
# 이 앱의 logger.info는 어디에도 출력되지 않았고, logger.warning만 logging의
# lastResort 핸들러를 타고 우연히 보이던 상태였다. 운영 기본 레벨을 INFO로
# 맞춘다(observability.md). uvicorn·uvicorn.access는 propagate=False라 여기에
# 핸들러를 달아도 접근 로그가 두 번 찍히지 않는다.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)

app = FastAPI()

from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

# 라우터가 dict detail로 코드를 직접 주지 않은 응답에 붙일 기본값.
# 프론트는 message가 아니라 code로 분기하므로(api-contract.md) 코드가 없거나
# 전부 INTERNAL_ERROR면 404와 500을 구분할 방법이 없다.
_DEFAULT_ERROR_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_FAILED",
    429: "RATE_LIMIT_EXCEEDED",
}


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc: StarletteHTTPException):
    # FastAPI의 HTTPException은 Starlette 것의 하위 클래스다. 상위 클래스에
    # 걸어야 라우터 자신이 던지는 404·405까지 같은 봉투로 나간다 — 하위
    # 클래스에만 걸면 그것들이 {"detail": ...} 그대로 새어나간다.
    if isinstance(exc.detail, dict):
        error = exc.detail
    else:
        error = {
            "code": _DEFAULT_ERROR_CODES.get(exc.status_code, "INTERNAL_ERROR"),
            "message": str(exc.detail),
        }
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "data": None, "error": error},
        # 405는 Allow 헤더를 달고 온다. 버리면 규격 위반이다.
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    # 어느 필드가 왜 틀렸는지는 details로 내린다. 메시지 문자열을 파싱하게
    # 만들면 서버 문구를 고칠 때마다 프론트가 깨진다.
    details = [
        # loc는 ("body", "email") 꼴이다. 첫 칸은 위치(body/query/path)라 필드명이 아니다.
        {"field": ".".join(str(p) for p in err["loc"][1:]) or None, "code": err["type"]}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "data": None,
            "error": {
                "code": "VALIDATION_FAILED",
                "message": "입력값을 확인해주세요",
                "details": details,
            },
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception):
    # 스택 트레이스는 서버 로그에만 남긴다. 응답에 실으면 내부 경로와 접속
    # 정보가 그대로 새어나간다(api-contract.md).
    logger.exception("처리하지 못한 예외: %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "data": None,
            "error": {"code": "INTERNAL_ERROR", "message": "서버 오류가 발생했습니다."},
        },
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
app.include_router(commitments_router)
app.include_router(assistant_router)


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


def _raise_ai_budget_exhausted() -> NoReturn:
    """소진 응답은 전 경로가 같아야 한다. 프론트는 message가 아니라 code로
    분기하므로 경로마다 코드가 다르면 화면이 소진을 한 가지로 다룰 수 없다.

    500이 아니라 429인 이유: 요약·비서·채팅이 같은 무료 티어 할당량을 나눠
    써서 사용자는 몇 건 만에 이 상태를 만난다. 일반 서버 오류로 보이면 파일이
    잘못됐다고 생각하고 다른 파일로 계속 재시도한다.
    """
    raise HTTPException(
        status_code=429,
        detail={
            "code": "AI_DAILY_BUDGET_EXHAUSTED",
            "message": "오늘 AI 한도를 다 썼습니다. 내일 다시 이용해주세요.",
        },
    )


def _classify_or_default(summary_text: str) -> str:
    """분류 폴백. 예산이 소진돼 있으면 '기타'로 강등한다.

    요청 전체를 429로 끝내지 않는 이유: 여기까지 왔다는 건 요약이 이미 예산을
    태워 완성됐다는 뜻이다. 분류는 다른 모든 실패에서 이미 '기타'로 떨어지는
    장식 필드인데(gemini_service.classify_document_category), 소진일 때만
    요청을 죽이면 사용자는 태운 예산과 다 만든 요약을 함께 잃는다.
    """
    try:
        return gemini_service.classify_document_category(
            summary_text, claim=call_budget.user_claimer()
        )
    except gemini_service.QuotaExceeded:
        logger.warning(
            "AI 예산 소진으로 문서 분류를 건너뛴다 — category=기타",
            extra={"event": "document.classify.budget_exhausted"},
        )
        return "기타"


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

    try:
        structured, summary_text = await gemini_service.summarize_upload(
            file, prompt, claim=call_budget.user_claimer()
        )
    except gemini_service.QuotaExceeded:
        _raise_ai_budget_exhausted()

    # 분류는 요약 응답에 함께 온다. classify_document_category는 구조화 파싱이
    # 실패해 structured가 없을 때만 쓰는 폴백이다 — 그때만 모델을 한 번 더
    # 부른다. 실측 1,637ms짜리 호출이라 정상 경로에서는 뺐다.
    category = category or (structured or {}).get("category")
    if not category:
        category = _classify_or_default(summary_text)

    doc = Document(
        group_id=group_id,
        source_type=source_type,
        category=category,
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

    created_commitments: list[Commitment] = []
    if structured:
        # 약속 추출이 깨져도 요약은 살아야 한다. 요약을 인질로 잡지 않는다.
        try:
            created_commitments = commitment_service.create_commitments(
                db,
                group_id=group_id,
                items=structured.get("commitments") or [],
                source_type=source_type,
                source_id=doc.id,
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.warning(
                "약속 저장 실패",
                extra={"event": "commitment.create.failed", "document_id": doc.id},
                exc_info=True,
            )
            created_commitments = []

    return {
        "id": doc.id,
        "filename": doc.filename,
        "summary": doc.summary,
        "category": doc.category,
        "structured": structured,
        "created_todos": [_serialize_todo(t) for t in created_todos],
        "created_commitments": len(created_commitments),
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
    require_group_member(current_user, group_id, db)

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
    require_group_member(current_user, group_id, db)

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
    require_group_member(current_user, group_id, db)
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
    if doc.group_id is None:
        # 전사 문서 개념을 없앤다. 지울 주체가 정의되지 않는다.
        raise HTTPException(
            status_code=403,
            detail={
                "code": "DOCUMENT_DELETE_FORBIDDEN",
                "message": "팀에 속하지 않은 문서는 삭제할 수 없습니다.",
            },
        )
    require_group_member(current_user, doc.group_id, db)
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
    require_group_member(current_user, group_id, db)
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
    require_group_member(current_user, body.group_id, db)

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
    require_group_member(current_user, todo.group_id, db)
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
    require_group_member(current_user, todo.group_id, db)
    db.delete(todo)
    db.commit()
    return {"deleted": True}


class ScheduleUpdate(BaseModel):
    title: str | None = None
    scheduled_date: str | None = None


class ScheduleCreate(BaseModel):
    title: str
    scheduled_date: str
    group_id: int


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
    require_group_member(current_user, body.group_id, db)
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
    require_group_member(current_user, group_id, db)
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
    if schedule.group_id is None:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "SCHEDULE_EDIT_FORBIDDEN",
                "message": "팀에 속하지 않은 일정은 수정할 수 없습니다.",
            },
        )
    require_group_member(current_user, schedule.group_id, db)
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
    if schedule.group_id is None:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "SCHEDULE_EDIT_FORBIDDEN",
                "message": "팀에 속하지 않은 일정은 수정할 수 없습니다.",
            },
        )
    require_group_member(current_user, schedule.group_id, db)
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


class ChatRoomMemberCreate(BaseModel):
    user_id: int


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


def _serialize_room(room: ChatRoom, last: ChatMessage | None, member_count: int) -> dict:
    return {
        "id": room.id,
        "group_id": room.group_id,
        "name": room.name,
        "ai_mode": room.ai_mode,
        "member_count": member_count,
        "created_at": room.created_at.isoformat(),
        "last_message": _serialize_message(last) if last else None,
    }


def _serialize_room_member(user: User, room: ChatRoom) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "is_owner": user.id == room.created_by,
    }


def _get_room_or_404(room_id: int, db: Session) -> ChatRoom:
    """방을 찾으면 돌려주고, 없으면 404를 던진다."""
    room = db.get(ChatRoom, room_id)
    if not room:
        raise HTTPException(
            status_code=404,
            detail={"code": "CHAT_ROOM_NOT_FOUND", "message": "채팅방을 찾을 수 없습니다."},
        )
    return room


def _require_room_access(user: User, room_id: int, db: Session) -> ChatRoom:
    """방을 찾고 그룹 멤버십과 방 초대 여부까지 확인한 뒤 방을 돌려준다."""
    room = _get_room_or_404(room_id, db)
    # 그룹을 먼저 본다. 그룹 밖 사람에게 "초대되지 않았다"고 알려주면 방의 존재가 새어나간다.
    require_group_member(user, room.group_id, db)
    if not db.get(ChatRoomMember, {"room_id": room.id, "user_id": user.id}):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "CHAT_ROOM_FORBIDDEN",
                "message": "이 채팅방에 초대되지 않았습니다.",
            },
        )
    return room


@app.get("/chat/rooms")
def list_chat_rooms(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """내가 초대된 방만, 마지막 메시지 미리보기까지 함께 내려준다."""
    require_group_member(current_user, group_id, db)

    rooms = db.scalars(
        select(ChatRoom)
        .join(ChatRoomMember, ChatRoomMember.room_id == ChatRoom.id)
        .where(ChatRoom.group_id == group_id, ChatRoomMember.user_id == current_user.id)
        .order_by(ChatRoom.created_at.asc())
    ).all()

    counts = dict(
        db.execute(
            select(ChatRoomMember.room_id, func.count())
            .where(ChatRoomMember.room_id.in_([r.id for r in rooms]))
            .group_by(ChatRoomMember.room_id)
        ).all()
    )

    result = []
    for room in rooms:
        last = db.scalars(
            select(ChatMessage)
            .where(ChatMessage.room_id == room.id)
            .order_by(ChatMessage.created_at.desc())
            .limit(1)
        ).first()
        result.append(_serialize_room(room, last, counts.get(room.id, 0)))
    return result


@app.post("/chat/rooms")
def create_chat_room(
    body: ChatRoomCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_group_member(current_user, body.group_id, db)

    name = body.name.strip()
    if not name:
        raise HTTPException(
            status_code=400,
            detail={"code": "CHAT_ROOM_NAME_REQUIRED", "message": "채팅방 이름이 비어 있습니다."},
        )

    room = ChatRoom(group_id=body.group_id, name=name, created_by=current_user.id)
    db.add(room)
    db.flush()
    db.add(ChatRoomMember(room_id=room.id, user_id=current_user.id))
    db.commit()
    db.refresh(room)
    return _serialize_room(room, None, 1)


@app.delete("/chat/rooms/{room_id}")
def delete_chat_room(
    room_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room = _get_room_or_404(room_id, db)
    # 생성자는 방에 속할 것으로 가정하고 full access check 수행
    if room.created_by == current_user.id:
        _require_room_access(current_user, room_id, db)
    else:
        # 생성자가 아니면 admin인지만 확인
        require_group_admin(
            current_user, room.group_id, db,
            code="CHAT_ROOM_DELETE_FORBIDDEN",
            message="방을 만든 사람이나 팀 관리자만 삭제할 수 있습니다.",
        )

    _delete_room_cascade(db, room)
    db.commit()
    return {"deleted": True}


def _delete_room_cascade(db: Session, room: ChatRoom) -> None:
    """자식 행을 먼저 지워야 외래키 제약에 걸리지 않는다. 커밋은 호출부가 한다.

    Commitment.room_id는 DB의 ON DELETE SET NULL에 기대지 않고 여기서
    애플리케이션이 직접 NULL로 만든다 — SQLite는 기본적으로 FK 제약을
    강제하지 않아 그 캐스케이드가 발동하지 않고, 발동하는 Postgres와
    엔진마다 동작이 갈리게 된다.

    지켜야 하는 불변식은 문장 순서가 아니라 **원자성**이다. 여기 있는
    NULL 처리와 삭제가 한 트랜잭션에서 함께 커밋되는 한, "멤버는 이미
    없는데 room_id는 남아있는"(= 아무에게도 안 보이는) 상태는 밖에서
    관측되지 않는다. 실제로 마지막 멤버 이탈 경로(remove_room_member)는
    멤버 행을 먼저 지우고 이 함수를 부르는데도 무해한 이유가 그것이다.
    중간에 db.commit()을 끼워 넣으면 그때 진짜 창이 열린다.
    """
    for commitment in db.scalars(
        select(Commitment).where(Commitment.room_id == room.id)
    ).all():
        commitment.room_id = None
    for message in db.scalars(select(ChatMessage).where(ChatMessage.room_id == room.id)).all():
        db.delete(message)
    for member in db.scalars(
        select(ChatRoomMember).where(ChatRoomMember.room_id == room.id)
    ).all():
        db.delete(member)
    db.delete(room)


@app.get("/chat/rooms/{room_id}/members")
def list_room_members(
    room_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room = _require_room_access(current_user, room_id, db)
    members = db.scalars(
        select(User)
        .join(ChatRoomMember, ChatRoomMember.user_id == User.id)
        .where(ChatRoomMember.room_id == room_id)
        .order_by(ChatRoomMember.created_at.asc())
    ).all()
    return [_serialize_room_member(u, room) for u in members]


@app.post("/chat/rooms/{room_id}/members")
def invite_room_member(
    room_id: int,
    body: ChatRoomMemberCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """방에 이미 있는 사람이면 누구나 초대할 수 있다."""
    room = _require_room_access(current_user, room_id, db)

    target = db.get(User, body.user_id)
    if not target:
        raise HTTPException(
            status_code=404,
            detail={"code": "USER_NOT_FOUND", "message": "사용자를 찾을 수 없습니다."},
        )
    # 그룹 밖 사람을 방에 넣으면 그룹 경계가 방을 통해 뚫린다. 그룹 초대가 먼저다.
    if not db.get(GroupMembership, {"user_id": target.id, "group_id": room.group_id}):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "CHAT_ROOM_INVITE_NOT_IN_GROUP",
                "message": "이 그룹에 속한 사람만 방에 초대할 수 있습니다.",
            },
        )
    if db.get(ChatRoomMember, {"room_id": room_id, "user_id": target.id}):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CHAT_ROOM_MEMBER_EXISTS",
                "message": "이미 이 방에 있는 사람입니다.",
            },
        )

    db.add(ChatRoomMember(room_id=room_id, user_id=target.id))
    db.commit()
    return _serialize_room_member(target, room)


@app.delete("/chat/rooms/{room_id}/members/{user_id}")
def remove_room_member(
    room_id: int,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """나가기는 누구나, 내보내기는 방을 만든 사람이나 관리자만."""
    room = _get_room_or_404(room_id, db)

    # 본인 또는 생성자가 접근하는 경우, 방에 속해있는지 확인
    if user_id == current_user.id or room.created_by == current_user.id:
        _require_room_access(current_user, room_id, db)
    else:
        # 다른 사람을 내보내려는 경우, admin인지만 확인
        require_group_admin(
            current_user, room.group_id, db,
            code="CHAT_ROOM_MEMBER_REMOVE_FORBIDDEN",
            message="방을 만든 사람이나 팀 관리자만 다른 사람을 내보낼 수 있습니다.",
        )

    membership = db.get(ChatRoomMember, {"room_id": room_id, "user_id": user_id})
    if not membership:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "CHAT_ROOM_MEMBER_NOT_FOUND",
                "message": "이 방에 없는 사람입니다.",
            },
        )

    db.delete(membership)
    db.flush()

    # 아무도 없는 방은 누구도 다시 열 수 없다. 남겨두면 조회 불가능한 행만 쌓인다.
    remaining = db.scalar(
        select(func.count()).select_from(ChatRoomMember).where(ChatRoomMember.room_id == room_id)
    )
    room_deleted = remaining == 0
    if room_deleted:
        _delete_room_cascade(db, room)

    db.commit()
    return {"removed": True, "room_deleted": room_deleted}


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


def _recent_history(
    db: Session, room_id: int, limit: int = 20, exclude_id: int | None = None
) -> list[dict]:
    query = select(ChatMessage).where(ChatMessage.room_id == room_id)
    if exclude_id is not None:
        query = query.where(ChatMessage.id != exclude_id)
    recent = db.scalars(
        query.order_by(ChatMessage.created_at.desc()).limit(limit)
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
        summary = gemini_service.summarize_conversation(
            _recent_history(db, room.id), claim=call_budget.user_claimer()
        )
        return _post_bot_message(db, room.id, summary)

    if command == "/문서":
        title = argument or "채팅 회의록"
        structured = gemini_service.draft_document_from_conversation(
            _recent_history(db, room.id), title, claim=call_budget.user_claimer()
        )
        if not structured:
            return _post_bot_message(
                db, room.id, "문서로 만들 대화가 부족합니다. 대화가 쌓인 뒤 다시 시도해주세요."
            )

        summary_text = gemini_service.render_summary_text(structured)
        doc = Document(
            group_id=room.group_id,
            source_type="document",
            # 분류는 초안 응답에 함께 온다(_SUMMARY_SCHEMA에 category가 있다).
            # 업로드 경로와 같은 폴백 형태다 — 구조화 파싱이 category를 못
            # 채웠을 때만 모델을 한 번 더 부른다.
            category=structured.get("category") or _classify_or_default(summary_text),
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
        actions = gemini_service.extract_chat_actions(
            argument, claim=call_budget.user_claimer()
        )
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
        reply = gemini_service.generate_bot_reply(
            _recent_history(db, room.id), argument, claim=call_budget.user_claimer()
        )
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
    # 명령어 넷(/요약·/문서·/할일·/질문)과 일반 메시지가 모두 예산을 태운다.
    # 소진을 여기서 안 잡으면 전역 핸들러가 500으로 받아, 이미 저장된 사용자
    # 메시지 위에 "응답만 실패"가 남고 메시지마다 스택 트레이스가 찍힌다.
    try:
        if content.startswith("/"):
            command, _, argument = content.partition(" ")
            bot_message = _handle_command(db, room, command.strip(), argument.strip())
        elif room.ai_mode:
            # AI가 방에 들어와 있을 때만 대화를 읽는다. 평소엔 Gemini를 호출하지 않는다.
            # 답변과 액션 추출을 한 번에 받는다 — 나눠 부르면 메시지 하나가
            # 하루 한도에서 2건을 먹는다.
            # 방금 저장한 메시지는 [메시지]로 따로 주므로 [지난 대화]에서 뺀다.
            # 겹쳐 두면 같은 문장이 "새로 뽑을 것"과 "이미 등록된 것"에 동시에 걸린다.
            turn = gemini_service.chat_reply_with_actions(
                _recent_history(db, room_id, exclude_id=user_message.id),
                content,
                claim=call_budget.user_claimer(),
            )
            _apply_extracted_actions(db, group_id, turn)
            db.commit()
            # 실패는 이제 안내 문구를 싣고 온다. 빈 문자열은 모델이 정말 빈 답을
            # 준 경우뿐이고, 그때 빈 말풍선을 남기지 않는다.
            if turn["reply"]:
                bot_message = _post_bot_message(db, room_id, turn["reply"])
    except gemini_service.QuotaExceeded:
        _raise_ai_budget_exhausted()

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
