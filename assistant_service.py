"""비서가 볼 업무 데이터를 모으고, 모델이 낸 액션을 검증한다.

이 모듈은 Gemini를 모른다. 모델 호출은 gemini_service, HTTP는 routers/assistant가
맡는다. 그래야 컨텍스트 수집을 모델 없이 테스트할 수 있다.
"""

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


def build_context(db: Session, group_id: int) -> dict:
    today = commitment_service.today_kst()
    return {
        "today": today.isoformat(),
        "commitments": _commitments(db, group_id, today),
        "todos": _todos(db, group_id),
        "schedules": _schedules(db, group_id, today),
        "clients": _clients(db, group_id),
    }


def _commitments(db: Session, group_id: int, today: date) -> list[dict]:
    # status별로 각각 상한을 둔다. 한 덩어리로 자르면 proposed가 많은 팀에서
    # confirmed가 통째로 밀려난다.
    rows: list[dict] = []
    for status in ("proposed", "confirmed"):
        stmt = (
            select(Commitment, Client.name)
            .join(Client, Client.id == Commitment.client_id, isouter=True)
            .where(Commitment.group_id == group_id, Commitment.status == status)
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
        lines.append(
            f"- id={c['id']} | {c['content']} | 고객사={c['client_name'] or '미지정'}"
            f" | 기한={c['due_date'] or '없음'} | 상태={c['status']}"
            f" | 출처={c['source_type']}" + (f" | {','.join(flags)}" if flags else "")
        )

    lines += ["", "[할 일]"]
    if not context["todos"]:
        lines.append("(없음)")
    for t in context["todos"]:
        lines.append(f"- id={t['id']} | {t['content']} | 기한={t['due_date'] or '없음'}")

    lines += ["", "[일정]"]
    if not context["schedules"]:
        lines.append("(없음)")
    for s in context["schedules"]:
        lines.append(f"- id={s['id']} | {s['title']} | {s['scheduled_date']}")

    lines += ["", "[클라이언트]", ", ".join(context["clients"]) or "(없음)"]
    return "\n".join(lines)
