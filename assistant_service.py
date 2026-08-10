"""비서가 볼 업무 데이터를 모으고, 모델이 낸 액션을 검증한다.

이 모듈은 Gemini를 모른다. 모델 호출은 gemini_service, HTTP는 routers/assistant가
맡는다. 그래야 컨텍스트 수집을 모델 없이 테스트할 수 있다.
"""

import uuid
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

import commitment_service
from models import Client, Commitment, Schedule, Todo

# 매 메시지마다 전량을 프롬프트에 싣는다. 토큰이 곧 비용이고 Gemini 무료 티어에
# 분당 한도가 있어 상한이 필요하다.
CONTEXT_COMMITMENT_LIMIT = 100
CONTEXT_TODO_LIMIT = 50
CONTEXT_SCHEDULE_LIMIT = 30
# 사용자·비서 메시지를 합쳐 배열 항목 20개(약 10왕복).
HISTORY_MESSAGE_LIMIT = 20

# NULL을 뒤로 보내는 값. SQLite가 NULLS LAST를 지원하지 않아 coalesce로 처리한다.
_FAR_FUTURE = date(9999, 12, 31)


def build_context(db: Session, group_id: int, user_id: int) -> dict:
    today = commitment_service.today_kst()
    return {
        "today": today.isoformat(),
        "commitments": _commitments(db, group_id, user_id, today),
        "todos": _todos(db, group_id),
        "schedules": _schedules(db, group_id, today),
        "clients": _clients(db, group_id),
    }


def _commitments(db: Session, group_id: int, user_id: int, today: date) -> list[dict]:
    # status별로 각각 상한을 둔다. 한 덩어리로 자르면 proposed가 많은 팀에서
    # confirmed가 통째로 밀려난다.
    #
    # 그룹 소속만으로는 부족하다 — 이 저장소의 가시성은 group_id + 채팅방
    # 멤버십 2단이다(commitment_service.visible_commitment_filter). 여기서
    # 빠뜨리면 비공개 방에서 나온 약속 원문이 비멤버에게도 프롬프트로 샌다.
    rows: list[dict] = []
    for status in ("proposed", "confirmed"):
        stmt = (
            select(Commitment, Client.name)
            .join(Client, Client.id == Commitment.client_id, isouter=True)
            .where(Commitment.group_id == group_id, Commitment.status == status)
            .where(commitment_service.visible_commitment_filter(user_id))
            .order_by(
                func.coalesce(Commitment.due_date, _FAR_FUTURE).asc(),
                Commitment.id.asc(),
            )
            .limit(CONTEXT_COMMITMENT_LIMIT)
        )
        for commitment, client_name in db.execute(stmt).all():
            is_overdue, is_due_soon = commitment_service.due_flags(commitment, today)
            rows.append(
                {
                    "id": commitment.id,
                    "content": commitment.content,
                    "client_name": client_name,
                    "due_date": commitment.due_date.isoformat() if commitment.due_date else None,
                    "status": commitment.status,
                    "source_type": commitment.source_type,
                    "is_overdue": is_overdue,
                    "is_due_soon": is_due_soon,
                }
            )
    return rows


def _todos(db: Session, group_id: int) -> list[dict]:
    stmt = (
        select(Todo)
        .where(Todo.group_id == group_id, Todo.is_done.is_(False))
        .order_by(func.coalesce(Todo.due_date, _FAR_FUTURE).asc(), Todo.id.asc())
        .limit(CONTEXT_TODO_LIMIT)
    )
    return [
        {
            "id": t.id,
            "content": t.content,
            "due_date": t.due_date.isoformat() if t.due_date else None,
        }
        for t in db.execute(stmt).scalars().all()
    ]


def _schedules(db: Session, group_id: int, today: date) -> list[dict]:
    # group_id가 NULL인 전사 일정도 함께 읽는다. 기존 GET /schedules가 그렇게
    # 동작해 사용자 화면에 이미 섞여 보인다 — 비서가 다른 걸 보면 답이 어긋난다.
    stmt = (
        select(Schedule)
        .where(
            or_(Schedule.group_id == group_id, Schedule.group_id.is_(None)),
            Schedule.scheduled_date >= today,
        )
        .order_by(Schedule.scheduled_date.asc(), Schedule.id.asc())
        .limit(CONTEXT_SCHEDULE_LIMIT)
    )
    return [
        {"id": s.id, "title": s.title, "scheduled_date": s.scheduled_date.isoformat()}
        for s in db.execute(stmt).scalars().all()
    ]


def _clients(db: Session, group_id: int) -> list[str]:
    stmt = select(Client.name).where(Client.group_id == group_id).order_by(Client.name.asc())
    return list(db.execute(stmt).scalars().all())


def _flatten(text: str) -> str:
    """개행을 공백으로 바꾼다. DB에서 온 텍스트(할 일·약속·클라이언트명 등)에
    개행과 "[질문]" 같은 구획 표시가 섞이면 프롬프트 구조를 흉내 내 모델을
    속일 수 있다 — 한 줄로 눌러 그 여지를 없앤다."""
    return " ".join(text.splitlines())


def render_context(context: dict) -> str:
    """프롬프트에 실을 평문. id를 함께 적는 것이 핵심이다 —
    모델이 문자열로 대상을 짐작하는 대신 id를 지목하게 만든다."""
    lines = [f"오늘: {context['today']}", "", "[약속]"]
    if not context["commitments"]:
        lines.append("(없음)")
    for c in context["commitments"]:
        flags = []
        if c["is_overdue"]:
            flags.append("기한초과")
        if c["is_due_soon"]:
            flags.append("마감임박")
        client_name = _flatten(c["client_name"]) if c["client_name"] else "미지정"
        lines.append(
            f"- id={c['id']} | {_flatten(c['content'])} | 고객사={client_name}"
            f" | 기한={c['due_date'] or '없음'} | 상태={c['status']}"
            f" | 출처={c['source_type']}" + (f" | {','.join(flags)}" if flags else "")
        )

    lines += ["", "[할 일]"]
    if not context["todos"]:
        lines.append("(없음)")
    for t in context["todos"]:
        lines.append(f"- id={t['id']} | {_flatten(t['content'])} | 기한={t['due_date'] or '없음'}")

    lines += ["", "[일정]"]
    if not context["schedules"]:
        lines.append("(없음)")
    for s in context["schedules"]:
        lines.append(f"- id={s['id']} | {_flatten(s['title'])} | {s['scheduled_date']}")

    lines += ["", "[클라이언트]", ", ".join(_flatten(n) for n in context["clients"]) or "(없음)"]
    return "\n".join(lines)


# 되돌릴 수 있는 것만 즉시 실행한다.
_SAFE_KINDS = frozenset({"todo_add", "todo_done", "schedule_add"})
# 삭제와 약속 전이는 승인을 받는다. 약속 전이는 _ALLOWED_TRANSITIONS에
# 역방향이 없어 한 번 넘어가면 앱 안에서 되돌릴 수 없다.
_CONFIRM_KINDS = frozenset({"todo_delete", "schedule_delete", "commitment_status"})

# 통과 액션 상한. 프론트가 safe 액션을 순차 자동 실행하므로, 모델이 할 일 수십
# 건에 한꺼번에 액션을 내면 클릭 없이 그만큼의 쓰기가 나간다. 초과분은 dropped로
# 합산한다. gemini_service._ASSISTANT_RESPONSE_SCHEMA의 actions maxItems와 값을
# 맞춘다 — 순환 import를 피하려 상수 자체는 공유하지 않는다.
MAX_ACTIONS = 10

_STATUS_LABELS = {
    "confirmed": "확정",
    "fulfilled": "이행 완료",
    "dismissed": "무시",
}


def validate_actions(
    db: Session, group_id: int, raw_actions: list[dict], user_id: int
) -> tuple[list[dict], int]:
    """모델이 낸 액션을 검증한다. (통과한 액션, 버린 개수)를 돌려준다.

    이 함수는 DB에 쓰지 않는다. 실행은 프론트가 기존 엔드포인트로 한다.
    """
    validated: list[dict] = []
    dropped = 0

    for raw in raw_actions or []:
        built = _build_action(db, group_id, user_id, raw if isinstance(raw, dict) else {})
        if built is None:
            dropped += 1
            continue
        if len(validated) >= MAX_ACTIONS:
            dropped += 1
            continue
        validated.append(built)

    return validated, dropped


def _action(kind: str, label: str, payload: dict, warning: str | None = None) -> dict:
    return {
        "id": uuid.uuid4().hex[:8],
        "risk": "safe" if kind in _SAFE_KINDS else "confirm",
        "kind": kind,
        "label": label,
        "warning": warning,
        "payload": payload,
    }


def _build_action(db: Session, group_id: int, user_id: int, raw: dict) -> dict | None:
    kind = raw.get("kind")
    if kind not in _SAFE_KINDS | _CONFIRM_KINDS:
        return None

    if kind == "todo_add":
        content = (raw.get("content") or "").strip()
        if not content:
            return None
        due = (raw.get("due_date") or "").strip() or None
        return _action(kind, f"할 일 추가: {content}", {"content": content, "due_date": due})

    if kind == "schedule_add":
        title = (raw.get("title") or "").strip()
        when = (raw.get("scheduled_date") or "").strip()
        if not title or not when:
            return None
        return _action(kind, f"일정 추가: {title} ({when})",
                       {"title": title, "scheduled_date": when})

    if kind in ("todo_done", "todo_delete"):
        todo = db.get(Todo, raw.get("todo_id") or 0)
        if todo is None or todo.group_id != group_id:
            return None
        if kind == "todo_done":
            return _action(kind, f"할 일 완료: {todo.content}",
                           {"todo_id": todo.id, "content": todo.content})
        return _action(kind, f"할 일 삭제: {todo.content}",
                       {"todo_id": todo.id, "content": todo.content},
                       warning="지운 할 일은 복구되지 않습니다")

    if kind == "schedule_delete":
        schedule = db.get(Schedule, raw.get("schedule_id") or 0)
        if schedule is None or schedule.group_id != group_id:
            return None
        return _action(kind, f"일정 삭제: {schedule.title}",
                       {"schedule_id": schedule.id, "title": schedule.title},
                       warning="지운 일정은 복구되지 않습니다")

    # commitment_status
    commitment = db.get(Commitment, raw.get("commitment_id") or 0)
    if commitment is None or commitment.group_id != group_id:
        return None
    # 그룹 소속만으로는 부족하다 — 비공개 채팅방 출처 약속은 방 멤버가 아니면
    # 안 보인다(commitment_service.is_commitment_visible). 여기서 빠뜨리면
    # 카드 라벨·payload에 content·client_name이 그대로 렌더돼 승인 전에
    # 이미 노출된다.
    if not commitment_service.is_commitment_visible(db, user_id, commitment):
        return None
    target = raw.get("to_status")
    # 통과시키면 사용자가 승인을 눌렀을 때 409를 본다 — 자기 잘못이 아닌 실패다.
    if not commitment_service.can_transition(commitment.status, target):
        return None

    client_name = None
    if commitment.client_id is not None:
        client = db.get(Client, commitment.client_id)
        client_name = client.name if client else None

    return _action(
        "commitment_status",
        f"약속을 {_STATUS_LABELS[target]}(으)로 바꿀까요?",
        {
            "commitment_id": commitment.id,
            "content": commitment.content,
            "client_name": client_name,
            "from_status": commitment.status,
            "to_status": target,
        },
        warning=f"{_STATUS_LABELS[target]} 처리는 되돌릴 수 없습니다",
    )
