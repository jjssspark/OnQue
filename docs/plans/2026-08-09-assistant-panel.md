# 우측 패널 AI 비서 Implementation Plan


**Goal:** 우측 상시 패널에 내 업무 데이터를 아는 1:1 AI 비서를 넣는다. 물어보면 답하고, 시키면 제안하며, 위험한 변경은 승인을 받는다.

**Architecture:** 비서 엔드포인트(`POST /api/v1/assistant/messages`)는 **읽기 전용**이다. DB를 읽어 컨텍스트를 만들고 Gemini에 물어 답과 액션 제안을 받는다. 실제 데이터 변경은 하나도 하지 않고, 프론트가 제안을 받아 **기존 엔드포인트**(`/todos`, `/schedules`, `/api/v1/commitments/bulk-status`)로 실행한다. 대화 기록은 클라이언트가 들고 다녀 서버에 세션 상태가 없다.

**Tech Stack:** FastAPI · SQLAlchemy 2.0 · google-genai (`gemini-2.5-flash`) · Next.js App Router · React · Tailwind

## Global Constraints

- **새 테이블 없음. 마이그레이션 없음.** 기존 테이블을 읽기만 한다
- **비서 엔드포인트는 DB를 쓰지 않는다** — `db.commit()`, `db.add()`, `db.delete()` 금지
- **응답에 URL이나 HTTP 메서드를 담지 않는다.** 프론트가 `kind`로 고정 분기한다
- **기존 에러 코드 문자열을 바꾸지 않는다.** 프론트가 `code`로 분기한다
- **UI에 이모지를 아이콘으로 쓰지 않는다.** 프롬프트에도 "이모지를 쓰지 않는다"를 넣는다
- 애니메이션은 `transform`·`opacity`만. 레이아웃 속성(`width`/`height`/`top`/`margin`) 금지
- **기존 `/chat`의 `@비서`(`generate_bot_reply`, `extract_chat_actions`)를 건드리지 않는다**
- `main.py` 라우트는 봉투가 **없고**(`request` 사용), `/api/v1` 라우트는 봉투가 **있다**(`requestEnveloped` 사용)
- 각 태스크는 **pytest 전체 통과** + `npx tsc --noEmit` 0건으로 끝난다. 프론트 태스크는 `npx next build --webpack`도 성공해야 한다
- 워크트리에서 `npm run build`는 Turbopack 심링크 문제로 실패한다(TS-026). 반드시 `npx next build --webpack`
- 테스트는 **포그라운드**로 돌린다. `run_in_background` 금지 — 대기하다 턴이 끝난다. timeout 500000ms
- 시작 시점 baseline: **195 passed**

## 상수 (여러 태스크가 공유)

```python
# assistant_service.py
CONTEXT_COMMITMENT_LIMIT = 100   # status별로 각각
CONTEXT_TODO_LIMIT = 50
CONTEXT_SCHEDULE_LIMIT = 30
HISTORY_MESSAGE_LIMIT = 20       # 사용자·비서 합쳐 배열 항목 20개
```

## 파일 구조

| 파일 | 책임 |
|---|---|
| `assistant_service.py` (신규) | 컨텍스트 수집, 프롬프트용 직렬화, 액션 검증. **Gemini를 모른다** |
| `gemini_service.py` (수정) | `answer_assistant()` 추가. 모델 호출과 스키마만 |
| `routers/assistant.py` (신규) | 엔드포인트. 권한·history 상한·502 매핑 |
| `main.py` (수정) | `include_router` 한 줄 |
| `tests/test_assistant_context.py` (신규) | 컨텍스트 수집 — 그룹 격리, 상한, 정렬 |
| `tests/test_assistant_gemini.py` (신규) | 모델 호출 — 프롬프트 구성, 실패 시 None |
| `tests/test_assistant_actions.py` (신규) | 액션 검증 — 없는 id, 타 그룹 id, 불법 전이, risk 분류 |
| `tests/test_assistant_routes.py` (신규) | 엔드포인트 — 403, 502, history 상한, 읽기 전용, 422 |
| `onque-frontend/lib/api.ts` (수정) | 타입 + `sendAssistantMessage` + `createSchedule` |
| `onque-frontend/components/AssistantPanel.tsx` (신규) | 대화 UI, 입력, 에러 |
| `onque-frontend/components/AssistantActionCard.tsx` (신규) | 액션 카드 렌더 + 실행 |
| `onque-frontend/components/SmartDashboardPanel.tsx` (수정) | 접힌 요약 + 비서 마운트 |

---

### Task 1: 컨텍스트 수집

**Files:**
- Create: `assistant_service.py`
- Test: `tests/test_assistant_context.py`

**Interfaces:**
- Consumes: 없음 (첫 태스크)
- Produces:
  - `build_context(db: Session, group_id: int) -> dict` — `{"today": str, "commitments": list[dict], "todos": list[dict], "schedules": list[dict], "clients": list[str]}`
  - `render_context(context: dict) -> str` — 프롬프트에 실을 평문
  - 상수 `CONTEXT_COMMITMENT_LIMIT`, `CONTEXT_TODO_LIMIT`, `CONTEXT_SCHEDULE_LIMIT`, `HISTORY_MESSAGE_LIMIT`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_assistant_context.py`:

```python
"""비서 컨텍스트 수집.

제일 중요한 단언은 그룹 격리다. A그룹에서 물었는데 B그룹 약속이 컨텍스트에
섞이면 정보 유출이고, 모델이 그걸 그대로 답에 옮긴다.
"""

from datetime import date, timedelta

import assistant_service
from models import Client, Commitment, Group, GroupMembership, Schedule, Todo, User


def _seed_group(db, name):
    user = User(email=f"{name}@onque.dev", password_hash="x", name=name)
    db.add(user)
    db.flush()
    group = Group(name=name, created_by=user.id)
    db.add(group)
    db.flush()
    db.add(GroupMembership(user_id=user.id, group_id=group.id, role="admin"))
    db.flush()
    return user, group


def _commitment(db, group_id, content, *, status="proposed", due=None, client_id=None):
    c = Commitment(
        group_id=group_id, content=content, status=status, due_date=due,
        source_type="chat", evidence="근거 원문", client_id=client_id,
    )
    db.add(c)
    db.flush()
    return c


def test_context_excludes_other_groups(db_session):
    """그룹 격리 — 이 단언이 깨지면 정보 유출이다."""
    _, group_a = _seed_group(db_session, "A팀")
    _, group_b = _seed_group(db_session, "B팀")

    _commitment(db_session, group_a.id, "A팀 약속")
    _commitment(db_session, group_b.id, "B팀 약속")
    db_session.add(Todo(group_id=group_a.id, content="A팀 할 일"))
    db_session.add(Todo(group_id=group_b.id, content="B팀 할 일"))
    db_session.add(Schedule(group_id=group_a.id, title="A팀 일정", scheduled_date=date.today()))
    db_session.add(Schedule(group_id=group_b.id, title="B팀 일정", scheduled_date=date.today()))
    db_session.add(Client(group_id=group_a.id, name="A고객"))
    db_session.add(Client(group_id=group_b.id, name="B고객"))
    db_session.commit()

    ctx = assistant_service.build_context(db_session, group_a.id)

    blob = assistant_service.render_context(ctx)
    assert "B팀" not in blob
    assert "B고객" not in blob
    assert [c["content"] for c in ctx["commitments"]] == ["A팀 약속"]
    assert [t["content"] for t in ctx["todos"]] == ["A팀 할 일"]
    assert [s["title"] for s in ctx["schedules"]] == ["A팀 일정"]
    assert ctx["clients"] == ["A고객"]


def test_context_includes_company_wide_schedules(db_session):
    """group_id가 NULL인 일정은 기존 GET /schedules가 이미 함께 보여준다.

    비서가 화면과 다른 걸 보면 답이 어긋난다.
    """
    _, group_a = _seed_group(db_session, "A팀")
    db_session.add(Schedule(group_id=None, title="전사 일정", scheduled_date=date.today()))
    db_session.commit()

    ctx = assistant_service.build_context(db_session, group_a.id)

    assert [s["title"] for s in ctx["schedules"]] == ["전사 일정"]


def test_commitments_sorted_by_due_date_with_nulls_last(db_session):
    """상한에 걸려 잘릴 때 급한 것부터 남아야 한다."""
    _, group = _seed_group(db_session, "A팀")
    today = date.today()
    _commitment(db_session, group.id, "기한 없음", due=None)
    _commitment(db_session, group.id, "나중", due=today + timedelta(days=10))
    _commitment(db_session, group.id, "급함", due=today + timedelta(days=1))
    db_session.commit()

    ctx = assistant_service.build_context(db_session, group.id)

    assert [c["content"] for c in ctx["commitments"]] == ["급함", "나중", "기한 없음"]


def test_context_respects_limits(db_session):
    _, group = _seed_group(db_session, "A팀")
    for i in range(assistant_service.CONTEXT_TODO_LIMIT + 10):
        db_session.add(Todo(group_id=group.id, content=f"할 일 {i}"))
    for i in range(assistant_service.CONTEXT_COMMITMENT_LIMIT + 10):
        _commitment(db_session, group.id, f"약속 {i}")
    db_session.commit()

    ctx = assistant_service.build_context(db_session, group.id)

    assert len(ctx["todos"]) == assistant_service.CONTEXT_TODO_LIMIT
    assert len(ctx["commitments"]) == assistant_service.CONTEXT_COMMITMENT_LIMIT


def test_done_todos_and_past_schedules_are_excluded(db_session):
    _, group = _seed_group(db_session, "A팀")
    db_session.add(Todo(group_id=group.id, content="끝난 일", is_done=True))
    db_session.add(Todo(group_id=group.id, content="남은 일", is_done=False))
    db_session.add(Schedule(group_id=group.id, title="지난 일정",
                            scheduled_date=date.today() - timedelta(days=1)))
    db_session.commit()

    ctx = assistant_service.build_context(db_session, group.id)

    assert [t["content"] for t in ctx["todos"]] == ["남은 일"]
    assert ctx["schedules"] == []


def test_confirmed_commitment_carries_due_flags(db_session):
    """proposed는 기한이 지나도 is_overdue가 False다 — 프롬프트가 이걸 알아야 한다."""
    _, group = _seed_group(db_session, "A팀")
    past = date.today() - timedelta(days=3)
    _commitment(db_session, group.id, "확정 지남", status="confirmed", due=past)
    _commitment(db_session, group.id, "미확인 지남", status="proposed", due=past)
    db_session.commit()

    ctx = assistant_service.build_context(db_session, group.id)
    by_content = {c["content"]: c for c in ctx["commitments"]}

    assert by_content["확정 지남"]["is_overdue"] is True
    assert by_content["미확인 지남"]["is_overdue"] is False


def test_client_name_is_resolved(db_session):
    _, group = _seed_group(db_session, "A팀")
    client = Client(group_id=group.id, name="A고객")
    db_session.add(client)
    db_session.flush()
    _commitment(db_session, group.id, "연결된 약속", client_id=client.id)
    _commitment(db_session, group.id, "미지정 약속", client_id=None)
    db_session.commit()

    ctx = assistant_service.build_context(db_session, group.id)
    by_content = {c["content"]: c for c in ctx["commitments"]}

    assert by_content["연결된 약속"]["client_name"] == "A고객"
    assert by_content["미지정 약속"]["client_name"] is None
```

- [ ] **Step 2: 실패를 확인한다**

Run: `./venv/bin/python -m pytest tests/test_assistant_context.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'assistant_service'`

- [ ] **Step 3: `assistant_service.py`를 만든다**

```python
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
```

- [ ] **Step 4: 통과를 확인한다**

Run: `./venv/bin/python -m pytest tests/test_assistant_context.py -q`
Expected: 7 passed

- [ ] **Step 5: 전체 스위트로 회귀를 본다**

Run: `./venv/bin/python -m pytest -q`
Expected: 202 passed (195 + 7)

- [ ] **Step 6: 커밋**

```bash
git add assistant_service.py tests/test_assistant_context.py
git commit -m "feat: 비서가 볼 업무 컨텍스트 수집

그룹 격리를 먼저 단언했다. A그룹에서 물었는데 B그룹 약속이 컨텍스트에
섞이면 모델이 그대로 답에 옮긴다.

마감 오름차순으로 정렬한다. created_at desc로 자르면 상한에 걸릴 때
마감 임박 건이 통째로 빠진다."
```

---

### Task 2: Gemini 질의응답

**Files:**
- Modify: `gemini_service.py` (파일 끝에 추가)
- Test: `tests/test_assistant_gemini.py`

**Interfaces:**
- Consumes: Task 1의 `render_context(context) -> str`
- Produces: `answer_assistant(context_text: str, history: list[dict], message: str) -> dict | None`
  - 성공: `{"reply": str, "actions": list[dict]}` — `actions`의 각 항목은 **검증 전 원본**이다
  - 실패: `None` (예외를 밖으로 던지지 않는다)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_assistant_gemini.py`:

```python
"""비서 모델 호출. 실제 Gemini를 부르지 않고 client를 목으로 막는다."""

import json
from types import SimpleNamespace

import gemini_service


def _fake_response(payload):
    return SimpleNamespace(text=json.dumps(payload))


def test_answer_assistant_returns_reply_and_actions(monkeypatch):
    captured = {}

    def fake_generate(*, model, contents, config):
        captured["contents"] = contents
        return _fake_response(
            {"reply": "약속은 2건입니다.", "actions": [{"kind": "todo_add", "content": "시안 정리"}]}
        )

    monkeypatch.setattr(gemini_service.client.models, "generate_content", fake_generate)

    result = gemini_service.answer_assistant("[약속]\n- id=1 | 시안", [], "약속 뭐 있지?")

    assert result["reply"] == "약속은 2건입니다."
    assert result["actions"][0]["kind"] == "todo_add"
    # 컨텍스트와 질문이 프롬프트에 실려야 한다.
    assert "id=1" in captured["contents"]
    assert "약속 뭐 있지?" in captured["contents"]


def test_answer_assistant_includes_history(monkeypatch):
    captured = {}

    def fake_generate(*, model, contents, config):
        captured["contents"] = contents
        return _fake_response({"reply": "네", "actions": []})

    monkeypatch.setattr(gemini_service.client.models, "generate_content", fake_generate)

    gemini_service.answer_assistant(
        "ctx",
        [{"role": "user", "content": "앞선 질문"}, {"role": "assistant", "content": "앞선 답"}],
        "그래서?",
    )

    assert "앞선 질문" in captured["contents"]
    assert "앞선 답" in captured["contents"]


def test_answer_assistant_returns_none_on_failure(monkeypatch):
    """실패를 빈 답으로 뭉개면 '모델이 죽음'과 '할 말 없음'이 구분되지 않는다."""

    def explode(*args, **kwargs):
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(gemini_service.client.models, "generate_content", explode)

    assert gemini_service.answer_assistant("ctx", [], "질문") is None


def test_answer_assistant_returns_none_on_malformed_json(monkeypatch):
    monkeypatch.setattr(
        gemini_service.client.models,
        "generate_content",
        lambda **kwargs: SimpleNamespace(text="이건 JSON이 아니다"),
    )

    assert gemini_service.answer_assistant("ctx", [], "질문") is None


def test_actions_default_to_empty_list(monkeypatch):
    monkeypatch.setattr(
        gemini_service.client.models,
        "generate_content",
        lambda **kwargs: _fake_response({"reply": "답만 있음"}),
    )

    result = gemini_service.answer_assistant("ctx", [], "질문")

    assert result == {"reply": "답만 있음", "actions": []}
```

- [ ] **Step 2: 실패를 확인한다**

Run: `./venv/bin/python -m pytest tests/test_assistant_gemini.py -q`
Expected: FAIL — `AttributeError: module 'gemini_service' has no attribute 'answer_assistant'`

- [ ] **Step 3: `gemini_service.py` 끝에 추가한다**

```python
_ASSISTANT_ACTION_SCHEMA = {
    "type": "OBJECT",
    "required": ["kind"],
    "properties": {
        "kind": {
            "type": "STRING",
            "enum": [
                "todo_add",
                "todo_done",
                "todo_delete",
                "schedule_add",
                "schedule_delete",
                "commitment_status",
            ],
        },
        "todo_id": {"type": "INTEGER", "description": "todo_done·todo_delete에만. 컨텍스트의 id."},
        "schedule_id": {"type": "INTEGER", "description": "schedule_delete에만. 컨텍스트의 id."},
        "commitment_id": {"type": "INTEGER", "description": "commitment_status에만. 컨텍스트의 id."},
        "content": {"type": "STRING", "description": "todo_add의 할 일 내용."},
        "title": {"type": "STRING", "description": "schedule_add의 일정 제목."},
        "due_date": {"type": "STRING", "description": "todo_add의 기한. YYYY-MM-DD. 없으면 빈 문자열."},
        "scheduled_date": {"type": "STRING", "description": "schedule_add의 날짜. YYYY-MM-DD."},
        "to_status": {
            "type": "STRING",
            "enum": ["confirmed", "fulfilled", "dismissed"],
            "description": "commitment_status에만.",
        },
    },
}

_ASSISTANT_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "required": ["reply"],
    "properties": {
        "reply": {"type": "STRING", "description": "사용자에게 보일 답변."},
        "actions": {"type": "ARRAY", "items": _ASSISTANT_ACTION_SCHEMA},
    },
}

_ASSISTANT_PROMPT = """
너는 대행사 담당자의 1:1 업무 비서다. 아래 [내 업무]에 있는 데이터만 근거로 답한다.

규칙:
- 주어진 데이터에 없는 것은 지어내지 않는다. 모르면 "그 정보는 없습니다"라고 말한다.
- 약속을 언급할 땐 출처(통화·문서·채팅)와 기한을 함께 말한다.
- 개수를 셀 땐 주어진 목록을 센다. 어림잡지 않는다.
- 상태가 proposed인 약속은 아직 사람이 확인하지 않은 것이라 기한초과 표시가 붙지 않는다.
  기한을 오늘 날짜와 직접 비교해서, 지났으면 지났다고 말해준다.
- 사용자가 무언가를 시키면 actions에 넣는다. 대상은 반드시 [내 업무]에 있는 id 중에서 고른다.
  id가 없으면 그 액션을 넣지 않고, 답변에서 어떤 것을 말하는지 되물어라.
- 단순히 묻기만 한 경우 actions는 빈 배열이다. 시키지도 않은 변경을 만들지 않는다.
- 답변은 2~4문장. 이모지, 마크다운 기호, 서론을 쓰지 않는다.
"""


def answer_assistant(context_text: str, history: list[dict], message: str) -> dict | None:
    """비서 답변과 액션 제안을 받는다.

    실패하면 None. 빈 답으로 뭉개면 호출자가 "모델이 죽음"과 "할 말 없음"을
    구분하지 못해, 사용자에게 정상인 척 빈 화면을 보여주게 된다.

    여기서 돌려주는 actions는 검증 전 원본이다 — 모델이 없는 id를 지어낼 수
    있으므로 assistant_service.validate_actions를 반드시 거쳐야 한다.
    """
    turns = "\n".join(
        f"{'나' if t.get('role') == 'user' else '비서'}: {t.get('content', '')}" for t in history
    )
    prompt = (
        f"{korean_date_context()}\n\n{_ASSISTANT_PROMPT}\n\n"
        f"[내 업무]\n{context_text}\n\n"
        f"[지난 대화]\n{turns or '(없음)'}\n\n"
        f"[질문]\n{message}"
    )
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_ASSISTANT_RESPONSE_SCHEMA,
            ),
        )
        data = json.loads(response.text)
        reply = (data.get("reply") or "").strip()
        if not reply:
            return None
        actions = data.get("actions")
        return {"reply": reply, "actions": actions if isinstance(actions, list) else []}
    except Exception:
        logger.warning(
            "비서 응답 실패",
            extra={"event": "assistant.answer.failed"},
            exc_info=True,
        )
        return None
```

- [ ] **Step 4: 통과를 확인한다**

Run: `./venv/bin/python -m pytest tests/test_assistant_gemini.py -q`
Expected: 5 passed

- [ ] **Step 5: 전체 스위트**

Run: `./venv/bin/python -m pytest -q`
Expected: 207 passed

- [ ] **Step 6: 커밋**

```bash
git add gemini_service.py tests/test_assistant_gemini.py
git commit -m "feat: 비서 질의응답 모델 호출

실패를 빈 답으로 뭉개지 않고 None을 돌려준다. 뭉개면 모델이 죽었는데도
사용자에게는 '할 말 없음'으로 보인다.

돌려주는 actions는 검증 전 원본이다 — 모델이 없는 id를 지어낼 수 있다."
```

---

### Task 3: 액션 검증

**Files:**
- Modify: `assistant_service.py` (파일 끝에 추가, 상단 import에 `uuid` 추가)
- Test: `tests/test_assistant_actions.py`

**Interfaces:**
- Consumes: Task 2의 `answer_assistant()`가 돌려주는 `actions` 원본
- Produces: `validate_actions(db: Session, group_id: int, raw_actions: list[dict]) -> tuple[list[dict], int]`
  - 반환: `(검증 통과한 액션 리스트, 버린 개수)`
  - 각 액션: `{"id": str, "risk": "safe"|"confirm", "kind": str, "label": str, "warning": str|None, "payload": dict}`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_assistant_actions.py`:

```python
"""모델이 낸 액션을 서버가 검증한다.

모델은 없는 id를 지어낼 수 있고, 불법 전이를 제안할 수 있다. 그대로 내려보내면
사용자가 승인을 눌렀을 때 자기 잘못이 아닌 실패를 본다.
"""

import assistant_service
from models import Commitment, Group, GroupMembership, Schedule, Todo, User


def _seed_group(db, name):
    user = User(email=f"{name}@onque.dev", password_hash="x", name=name)
    db.add(user)
    db.flush()
    group = Group(name=name, created_by=user.id)
    db.add(group)
    db.flush()
    db.add(GroupMembership(user_id=user.id, group_id=group.id, role="admin"))
    db.flush()
    return group


def _commitment(db, group_id, content, status="confirmed"):
    c = Commitment(
        group_id=group_id, content=content, status=status,
        source_type="chat", evidence="근거",
    )
    db.add(c)
    db.flush()
    return c


def test_add_actions_are_safe(db_session):
    group = _seed_group(db_session, "A팀")
    db_session.commit()

    actions, dropped = assistant_service.validate_actions(
        db_session, group.id,
        [{"kind": "todo_add", "content": "시안 정리", "due_date": "2026-08-20"}],
    )

    assert dropped == 0
    assert actions[0]["risk"] == "safe"
    assert actions[0]["payload"] == {"content": "시안 정리", "due_date": "2026-08-20"}
    assert actions[0]["warning"] is None
    assert actions[0]["id"]


def test_delete_and_status_actions_need_confirmation(db_session):
    group = _seed_group(db_session, "A팀")
    todo = Todo(group_id=group.id, content="지울 일")
    db_session.add(todo)
    commitment = _commitment(db_session, group.id, "완료할 약속")
    db_session.commit()

    actions, dropped = assistant_service.validate_actions(
        db_session, group.id,
        [
            {"kind": "todo_delete", "todo_id": todo.id},
            {"kind": "commitment_status", "commitment_id": commitment.id, "to_status": "fulfilled"},
        ],
    )

    assert dropped == 0
    assert [a["risk"] for a in actions] == ["confirm", "confirm"]
    # 되돌릴 수 없는 전이에는 경고가 붙는다.
    assert "되돌릴 수 없" in actions[1]["warning"]


def test_todo_done_is_safe_because_it_toggles_back(db_session):
    group = _seed_group(db_session, "A팀")
    todo = Todo(group_id=group.id, content="끝낼 일")
    db_session.add(todo)
    db_session.commit()

    actions, _ = assistant_service.validate_actions(
        db_session, group.id, [{"kind": "todo_done", "todo_id": todo.id}]
    )

    assert actions[0]["risk"] == "safe"


def test_unknown_id_is_dropped(db_session):
    group = _seed_group(db_session, "A팀")
    db_session.commit()

    actions, dropped = assistant_service.validate_actions(
        db_session, group.id, [{"kind": "todo_delete", "todo_id": 99999}]
    )

    assert actions == []
    assert dropped == 1


def test_other_groups_id_is_dropped(db_session):
    """타 그룹 id를 지목하면 버린다 — 통과시키면 남의 데이터를 지운다."""
    group_a = _seed_group(db_session, "A팀")
    group_b = _seed_group(db_session, "B팀")
    foreign = _commitment(db_session, group_b.id, "B팀 약속")
    foreign_todo = Todo(group_id=group_b.id, content="B팀 할 일")
    db_session.add(foreign_todo)
    db_session.commit()

    actions, dropped = assistant_service.validate_actions(
        db_session, group_a.id,
        [
            {"kind": "commitment_status", "commitment_id": foreign.id, "to_status": "fulfilled"},
            {"kind": "todo_delete", "todo_id": foreign_todo.id},
        ],
    )

    assert actions == []
    assert dropped == 2


def test_illegal_transition_is_dropped(db_session):
    """proposed -> fulfilled 는 _ALLOWED_TRANSITIONS에 없다."""
    group = _seed_group(db_session, "A팀")
    commitment = _commitment(db_session, group.id, "미확인 약속", status="proposed")
    db_session.commit()

    actions, dropped = assistant_service.validate_actions(
        db_session, group.id,
        [{"kind": "commitment_status", "commitment_id": commitment.id, "to_status": "fulfilled"}],
    )

    assert actions == []
    assert dropped == 1


def test_unknown_kind_is_dropped(db_session):
    group = _seed_group(db_session, "A팀")
    db_session.commit()

    actions, dropped = assistant_service.validate_actions(
        db_session, group.id, [{"kind": "drop_database"}]
    )

    assert actions == []
    assert dropped == 1


def test_add_action_without_content_is_dropped(db_session):
    group = _seed_group(db_session, "A팀")
    db_session.commit()

    actions, dropped = assistant_service.validate_actions(
        db_session, group.id,
        [{"kind": "todo_add", "content": "   "}, {"kind": "schedule_add", "title": "회의"}],
    )

    # 내용이 빈 할 일, 날짜 없는 일정 둘 다 버린다.
    assert actions == []
    assert dropped == 2


def test_validation_does_not_write_to_db(db_session):
    group = _seed_group(db_session, "A팀")
    todo = Todo(group_id=group.id, content="그대로 남을 일")
    db_session.add(todo)
    db_session.commit()

    assistant_service.validate_actions(
        db_session, group.id, [{"kind": "todo_delete", "todo_id": todo.id}]
    )

    assert db_session.get(Todo, todo.id) is not None
```

- [ ] **Step 2: 실패를 확인한다**

Run: `./venv/bin/python -m pytest tests/test_assistant_actions.py -q`
Expected: FAIL — `AttributeError: module 'assistant_service' has no attribute 'validate_actions'`

- [ ] **Step 3: `assistant_service.py` 상단 import에 `uuid`를 넣고 파일 끝에 추가한다**

```python
# 되돌릴 수 있는 것만 즉시 실행한다.
_SAFE_KINDS = frozenset({"todo_add", "todo_done", "schedule_add"})
# 삭제와 약속 전이는 승인을 받는다. 약속 전이는 _ALLOWED_TRANSITIONS에
# 역방향이 없어 한 번 넘어가면 앱 안에서 되돌릴 수 없다.
_CONFIRM_KINDS = frozenset({"todo_delete", "schedule_delete", "commitment_status"})

_STATUS_LABELS = {
    "confirmed": "확정",
    "fulfilled": "이행 완료",
    "dismissed": "무시",
}


def validate_actions(
    db: Session, group_id: int, raw_actions: list[dict]
) -> tuple[list[dict], int]:
    """모델이 낸 액션을 검증한다. (통과한 액션, 버린 개수)를 돌려준다.

    이 함수는 DB에 쓰지 않는다. 실행은 프론트가 기존 엔드포인트로 한다.
    """
    validated: list[dict] = []
    dropped = 0

    for raw in raw_actions or []:
        built = _build_action(db, group_id, raw if isinstance(raw, dict) else {})
        if built is None:
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


def _build_action(db: Session, group_id: int, raw: dict) -> dict | None:
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
```

- [ ] **Step 4: 통과를 확인한다**

Run: `./venv/bin/python -m pytest tests/test_assistant_actions.py -q`
Expected: 9 passed

- [ ] **Step 5: 전체 스위트**

Run: `./venv/bin/python -m pytest -q`
Expected: 216 passed

- [ ] **Step 6: 커밋**

```bash
git add assistant_service.py tests/test_assistant_actions.py
git commit -m "feat: 모델이 낸 액션을 서버가 검증

없는 id, 타 그룹 id, 불법 전이를 버린다. 통과시키면 사용자가 승인을 눌렀을
때 자기 잘못이 아닌 실패를 보고, 최악의 경우 남의 그룹 데이터를 건드린다.

삭제와 약속 전이는 confirm으로 분류한다 — 약속 전이는 역방향이 없다."
```

---

### Task 4: 엔드포인트

**Files:**
- Create: `routers/assistant.py`
- Modify: `main.py` — import와 `include_router` 각 한 줄
- Test: `tests/test_assistant_routes.py`

**Interfaces:**
- Consumes: `assistant_service.build_context`, `render_context`, `validate_actions`, `HISTORY_MESSAGE_LIMIT`; `gemini_service.answer_assistant`
- Produces: `POST /api/v1/assistant/messages` → `{"success": true, "data": {"reply": str, "actions": [...]}, "error": null}`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_assistant_routes.py`:

```python
"""비서 엔드포인트.

이 엔드포인트는 읽기 전용이다 — 실제 변경은 프론트가 기존 엔드포인트로 한다.
권한 검사와 전이 규칙을 두 벌로 유지하지 않기 위해서다.
"""

import gemini_service
from models import Commitment, Schedule, Todo


def _signup(client, email, name):
    return client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "password123", "name": name},
    ).json()["data"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _setup(client):
    owner = _signup(client, "owner@onque.dev", "주인")
    group_id = client.post(
        "/api/v1/groups", json={"name": "A팀"}, headers=_auth(owner["token"])
    ).json()["data"]["id"]
    return owner, group_id


def _ask(client, token, group_id, message="약속 뭐 있지?", history=None):
    return client.post(
        "/api/v1/assistant/messages",
        json={"group_id": group_id, "message": message, "history": history or []},
        headers=_auth(token),
    )


def test_answers_with_envelope(client, monkeypatch):
    owner, group_id = _setup(client)
    monkeypatch.setattr(
        gemini_service, "answer_assistant",
        lambda ctx, hist, msg: {"reply": "약속은 없습니다.", "actions": []},
    )

    res = _ask(client, owner["token"], group_id)

    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["reply"] == "약속은 없습니다."
    assert body["data"]["actions"] == []
    assert body["error"] is None


def test_non_member_gets_403(client, monkeypatch):
    owner, group_id = _setup(client)
    outsider = _signup(client, "outsider@onque.dev", "외부인")
    monkeypatch.setattr(
        gemini_service, "answer_assistant",
        lambda ctx, hist, msg: {"reply": "여기 오면 안 된다", "actions": []},
    )

    res = _ask(client, outsider["token"], group_id)

    assert res.status_code == 403
    assert res.json()["error"]["code"] == "GROUP_ACCESS_FORBIDDEN"


def test_gemini_failure_returns_502_envelope(client, monkeypatch):
    """실패를 조용히 넘기면 '답이 없음'과 '모델이 죽음'이 구분되지 않는다."""
    owner, group_id = _setup(client)
    monkeypatch.setattr(gemini_service, "answer_assistant", lambda ctx, hist, msg: None)

    res = _ask(client, owner["token"], group_id)

    assert res.status_code == 502
    assert res.json()["error"]["code"] == "ASSISTANT_UNAVAILABLE"


def test_history_is_capped_not_rejected(client, monkeypatch):
    """상한 초과는 사용자 잘못이 아니다. 422로 거절하지 않고 서버가 자른다."""
    import assistant_service

    owner, group_id = _setup(client)
    captured = {}

    def fake(ctx, hist, msg):
        captured["history"] = hist
        return {"reply": "네", "actions": []}

    monkeypatch.setattr(gemini_service, "answer_assistant", fake)
    long_history = [{"role": "user", "content": f"메시지 {i}"} for i in range(40)]

    res = _ask(client, owner["token"], group_id, history=long_history)

    assert res.status_code == 200
    assert len(captured["history"]) == assistant_service.HISTORY_MESSAGE_LIMIT
    # 잘라내되 최근 것을 남긴다.
    assert captured["history"][-1]["content"] == "메시지 39"


def test_empty_message_returns_422(client):
    owner, group_id = _setup(client)

    res = _ask(client, owner["token"], group_id, message="")

    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_FAILED"


def test_endpoint_does_not_write_to_db(client, db_session, monkeypatch):
    """비서 엔드포인트는 읽기 전용이다."""
    owner, group_id = _setup(client)
    db_session.add(Todo(group_id=group_id, content="그대로 남을 일"))
    db_session.commit()

    before = (
        db_session.query(Todo).count(),
        db_session.query(Schedule).count(),
        db_session.query(Commitment).count(),
    )

    # 모델이 삭제를 제안해도 엔드포인트는 실행하지 않는다.
    todo_id = db_session.query(Todo).first().id
    monkeypatch.setattr(
        gemini_service, "answer_assistant",
        lambda ctx, hist, msg: {
            "reply": "지울까요?",
            "actions": [{"kind": "todo_delete", "todo_id": todo_id}],
        },
    )

    res = _ask(client, owner["token"], group_id, message="그거 지워줘")

    assert res.status_code == 200
    assert res.json()["data"]["actions"][0]["risk"] == "confirm"
    db_session.expire_all()
    after = (
        db_session.query(Todo).count(),
        db_session.query(Schedule).count(),
        db_session.query(Commitment).count(),
    )
    assert before == after


def test_dropped_actions_are_reported_in_reply(client, monkeypatch):
    """조용히 사라지면 사용자는 비서가 무시했다고 생각한다."""
    owner, group_id = _setup(client)
    monkeypatch.setattr(
        gemini_service, "answer_assistant",
        lambda ctx, hist, msg: {
            "reply": "지우겠습니다.",
            "actions": [{"kind": "todo_delete", "todo_id": 99999}],
        },
    )

    res = _ask(client, owner["token"], group_id, message="그거 지워줘")

    body = res.json()["data"]
    assert body["actions"] == []
    assert "제외" in body["reply"]
```

- [ ] **Step 2: 실패를 확인한다**

Run: `./venv/bin/python -m pytest tests/test_assistant_routes.py -q`
Expected: FAIL — 전부 404 (라우터가 없다)

- [ ] **Step 3: `routers/assistant.py`를 만든다**

```python
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import assistant_service
import gemini_service
from auth import get_current_user
from db import get_db
from models import User
from permissions import require_group_member

router = APIRouter(prefix="/api/v1", tags=["assistant"])

logger = logging.getLogger(__name__)


class HistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class AssistantMessageBody(BaseModel):
    group_id: int
    message: str = Field(min_length=1, max_length=2000)
    history: list[HistoryTurn] = Field(default_factory=list)


@router.post("/assistant/messages")
def send_assistant_message(
    body: AssistantMessageBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """비서에게 묻는다. 이 엔드포인트는 DB를 쓰지 않는다 — 읽고 제안만 한다.

    실제 변경은 프론트가 기존 엔드포인트(/todos, /schedules,
    /api/v1/commitments/bulk-status)로 실행한다. 권한 검사와 상태 전이
    규칙을 두 벌로 유지하지 않기 위해서다.
    """
    require_group_member(current_user, body.group_id, db)

    context = assistant_service.build_context(db, body.group_id)
    # 상한 초과를 422로 거절하지 않는다. 대화가 길어진 건 사용자 잘못이 아니다.
    history = [t.model_dump() for t in body.history][-assistant_service.HISTORY_MESSAGE_LIMIT:]

    answer = gemini_service.answer_assistant(
        assistant_service.render_context(context), history, body.message
    )
    if answer is None:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "ASSISTANT_UNAVAILABLE",
                "message": "비서가 응답하지 못했습니다. 잠시 후 다시 시도해주세요.",
            },
        )

    actions, dropped = assistant_service.validate_actions(
        db, body.group_id, answer["actions"]
    )
    reply = answer["reply"]
    if dropped:
        # 조용히 사라지면 사용자는 비서가 요청을 무시했다고 생각한다.
        reply = f"{reply}\n\n(일부 제안은 적용할 수 없어 제외했습니다.)"
        logger.warning(
            "비서 액션 일부 제외",
            extra={"event": "assistant.actions.dropped", "group_id": body.group_id},
        )

    return {"success": True, "data": {"reply": reply, "actions": actions}, "error": None}
```

- [ ] **Step 4: `main.py`에 라우터를 등록한다**

`from routers.commitments import router as commitments_router` 아래에 추가:

```python
from routers.assistant import router as assistant_router
```

`app.include_router(commitments_router)` 아래에 추가:

```python
app.include_router(assistant_router)
```

- [ ] **Step 5: 통과를 확인한다**

Run: `./venv/bin/python -m pytest tests/test_assistant_routes.py -q`
Expected: 7 passed

- [ ] **Step 6: 전체 스위트**

Run: `./venv/bin/python -m pytest -q`
Expected: 223 passed

- [ ] **Step 7: 커밋**

```bash
git add routers/assistant.py main.py tests/test_assistant_routes.py
git commit -m "feat: 비서 엔드포인트

읽기 전용이다. 모델이 삭제를 제안해도 여기서 실행하지 않고 검증된 제안만
내려보낸다 — 실행은 프론트가 기존 엔드포인트로 한다.

history 상한 초과를 422로 거절하지 않고 서버가 자른다. 대화가 길어진 건
사용자 잘못이 아니다.

버린 액션은 답변에 밝힌다. 조용히 사라지면 무시당했다고 느낀다."
```

---

### Task 5: 프론트 API 배선

**Files:**
- Modify: `onque-frontend/lib/api.ts`

**Interfaces:**
- Consumes: Task 4의 `POST /api/v1/assistant/messages` 응답 형태
- Produces:
  - `AssistantAction`, `AssistantTurn`, `AssistantReply`, `AssistantActionKind` 타입
  - `sendAssistantMessage(groupId: number, message: string, history: AssistantTurn[]): Promise<AssistantReply>`
  - `createSchedule(groupId: number, title: string, scheduledDate: string): Promise<ScheduleItem>`

- [ ] **Step 1: 타입을 추가한다**

`lib/api.ts`의 타입 구역(`CommitmentRecord` 근처)에 추가:

```ts
export type AssistantActionKind =
  | 'todo_add'
  | 'todo_done'
  | 'todo_delete'
  | 'schedule_add'
  | 'schedule_delete'
  | 'commitment_status';

/** 서버가 검증을 마친 제안. payload는 kind마다 모양이 달라 실행 시점에 좁힌다. */
export type AssistantAction = {
  id: string;
  risk: 'safe' | 'confirm';
  kind: AssistantActionKind;
  label: string;
  warning: string | null;
  payload: Record<string, unknown>;
};

export type AssistantTurn = { role: 'user' | 'assistant'; content: string };

export type AssistantReply = { reply: string; actions: AssistantAction[] };
```

- [ ] **Step 2: 함수 두 개를 추가한다**

`bulkUpdateCommitments` 아래:

```ts
export function sendAssistantMessage(
  groupId: number,
  message: string,
  history: AssistantTurn[],
): Promise<AssistantReply> {
  return requestEnveloped<AssistantReply>('/api/v1/assistant/messages', {
    method: 'POST',
    body: JSON.stringify({ group_id: groupId, message, history }),
  });
}
```

`deleteSchedule` 위. **`/schedules`는 main.py 라우트라 봉투가 없다 — `requestEnveloped`가 아니라 `request`를 쓴다.**

```ts
export function createSchedule(
  groupId: number,
  title: string,
  scheduledDate: string,
): Promise<ScheduleItem> {
  return request('/schedules', {
    method: 'POST',
    body: JSON.stringify({ group_id: groupId, title, scheduled_date: scheduledDate }),
  });
}
```

- [ ] **Step 3: 타입 검사**

Run: `cd onque-frontend && npx tsc --noEmit`
Expected: 에러 0건

- [ ] **Step 4: 빌드**

Run: `cd onque-frontend && npx next build --webpack`
Expected: 성공

- [ ] **Step 5: 커밋**

```bash
git add onque-frontend/lib/api.ts
git commit -m "feat: 비서 API 래퍼와 createSchedule 추가

createSchedule은 백엔드에 엔드포인트가 있는데 프론트 래퍼가 없었다 —
지금까지 일정은 채팅 추출로만 만들어졌다.

/schedules는 main.py 라우트라 봉투가 없어 request를 쓴다."
```

---

### Task 6: 비서 대화 UI

**Files:**
- Create: `onque-frontend/components/AssistantPanel.tsx`
- Modify: `onque-frontend/components/SmartDashboardPanel.tsx` — 마지막 `</section>` 뒤, `</aside>` 앞에 마운트

**Interfaces:**
- Consumes: Task 5의 `sendAssistantMessage`, `AssistantTurn`, `AssistantAction`; `useWorkspace()`의 `currentGroupId`
- Produces: `<AssistantPanel />` — props 없음. 액션은 여기서 받아두기만 하고 렌더·실행은 Task 7이 붙인다

이 태스크가 끝나면 비서가 **패널 맨 아래에 붙어 실제로 대화가 된다.** 레이아웃 재배치는 Task 8이다.

- [ ] **Step 1: `AssistantPanel.tsx`를 만든다**

```tsx
'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { sendAssistantMessage, type AssistantAction, type AssistantTurn } from '@/lib/api';
import { useWorkspace } from '@/components/WorkspaceContext';

type Message = {
  role: 'user' | 'assistant';
  content: string;
  actions: AssistantAction[];
};

export function AssistantPanel() {
  const { currentGroupId } = useWorkspace();
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  // 그룹을 바꾸면 이전 그룹 대화를 이어가지 않는다. 맥락이 섞이면 비서가
  // 지금 그룹에 없는 데이터를 참조한다.
  useEffect(() => {
    setMessages([]);
    setError(null);
  }, [currentGroupId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' });
  }, [messages, pending]);

  const send = useCallback(async () => {
    const text = draft.trim();
    if (!text || pending || currentGroupId === null) return;

    const history: AssistantTurn[] = messages.map((m) => ({
      role: m.role,
      content: m.content,
    }));

    setMessages((prev) => [...prev, { role: 'user', content: text, actions: [] }]);
    setDraft('');
    setPending(true);
    setError(null);

    try {
      const reply = await sendAssistantMessage(currentGroupId, text, history);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: reply.reply, actions: reply.actions },
      ]);
    } catch (err) {
      // 친 문장을 입력창에 되돌려 놓는다. 날리면 다시 타이핑해야 한다.
      setDraft(text);
      setMessages((prev) => prev.slice(0, -1));
      setError(err instanceof Error ? err.message : '비서가 응답하지 못했습니다.');
    } finally {
      setPending(false);
    }
  }, [draft, pending, currentGroupId, messages]);

  if (currentGroupId === null) return null;

  return (
    <section className="flex min-h-0 flex-1 flex-col border-t border-border">
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-5 py-4">
        {messages.length === 0 && !pending && (
          <p className="text-xs leading-relaxed text-foreground/40">
            약속·할 일·일정에 대해 물어보세요. 예: A사한테 뭐 약속했더라?
          </p>
        )}

        {messages.map((m, i) => (
          <div key={i} className={m.role === 'user' ? 'text-right' : ''}>
            <p
              className={`inline-block max-w-[92%] whitespace-pre-wrap rounded-lg px-3 py-2 text-xs leading-relaxed ${
                m.role === 'user'
                  ? 'bg-accent/[0.12] text-foreground'
                  : 'bg-foreground/[0.04] text-foreground/90'
              }`}
            >
              {m.content}
            </p>
          </div>
        ))}

        {pending && <p className="text-xs text-foreground/40">비서가 확인하는 중입니다…</p>}

        {error && (
          <p role="alert" className="text-xs leading-relaxed text-red-300">
            {error}
          </p>
        )}

        <div ref={endRef} />
      </div>

      <div className="border-t border-border px-4 py-3">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send();
          }}
          className="flex items-center gap-2"
        >
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="무엇이든 물어보세요"
            aria-label="비서에게 물어보기"
            className="min-w-0 flex-1 rounded-lg border border-border bg-transparent px-3 py-2 text-xs text-foreground outline-none placeholder:text-foreground/30 focus:border-accent/50"
          />
          <button
            type="submit"
            disabled={pending || !draft.trim()}
            className="shrink-0 rounded-lg border border-accent/40 px-3 py-2 text-xs font-bold text-accent transition hover:bg-accent/[0.12] disabled:opacity-30"
          >
            보내기
          </button>
        </form>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: `SmartDashboardPanel.tsx`에 마운트한다**

import를 추가:

```tsx
import { AssistantPanel } from '@/components/AssistantPanel';
```

일정 섹션의 `</section>` 뒤, `</aside>` 앞에 넣는다:

```tsx
      <AssistantPanel />
```

- [ ] **Step 3: 타입 검사**

Run: `cd onque-frontend && npx tsc --noEmit`
Expected: 에러 0건

- [ ] **Step 4: 빌드**

Run: `cd onque-frontend && npx next build --webpack`
Expected: 성공

- [ ] **Step 5: 커밋**

```bash
git add onque-frontend/components/AssistantPanel.tsx onque-frontend/components/SmartDashboardPanel.tsx
git commit -m "feat: 우측 패널 비서 대화 UI

실패하면 사용자가 친 문장을 입력창에 되돌려 놓는다. 날리면 다시
타이핑해야 한다.

그룹을 바꾸면 대화를 비운다 — 맥락이 섞이면 비서가 지금 그룹에 없는
데이터를 참조한다."
```

---

### Task 7: 액션 카드와 실행

**Files:**
- Create: `onque-frontend/components/AssistantActionCard.tsx`
- Modify: `onque-frontend/components/AssistantPanel.tsx` — 액션 렌더와 safe 즉시 실행 배선

**Interfaces:**
- Consumes: Task 5의 `AssistantAction`, `createTodo`, `updateTodo`, `deleteTodo`, `createSchedule`, `deleteSchedule`, `bulkUpdateCommitments`; `useWorkspace()`의 `refresh`, `currentGroupId`
- Produces:
  - `<AssistantActionCard action={...} groupId={...} onChanged={...} />`
  - `applySafeAction(action: AssistantAction, groupId: number): Promise<number | null>`

- [ ] **Step 1: `AssistantActionCard.tsx`를 만든다**

```tsx
'use client';

import { useState } from 'react';
import {
  bulkUpdateCommitments,
  createSchedule,
  createTodo,
  deleteSchedule,
  deleteTodo,
  updateTodo,
  type AssistantAction,
} from '@/lib/api';

type State = 'idle' | 'running' | 'applied' | 'declined' | 'failed';

/** 서버가 kind를 정해서 내려보내고, 프론트는 여기서 고정 분기한다.
 * 응답에 URL을 담지 않는 이유다 — 모델 출력이 요청 경로에 닿지 않게 한다.
 * 생성 계열은 만들어진 id를 돌려준다(취소할 때 필요하다). */
export async function applySafeAction(
  action: AssistantAction,
  groupId: number,
): Promise<number | null> {
  const p = action.payload;
  switch (action.kind) {
    case 'todo_add': {
      const todo = await createTodo(
        groupId,
        p.content as string,
        (p.due_date as string | null) ?? undefined,
      );
      return todo.id;
    }
    case 'todo_done':
      await updateTodo(p.todo_id as number, { is_done: true });
      return null;
    case 'todo_delete':
      await deleteTodo(p.todo_id as number);
      return null;
    case 'schedule_add': {
      const schedule = await createSchedule(
        groupId,
        p.title as string,
        p.scheduled_date as string,
      );
      return schedule.id;
    }
    case 'schedule_delete':
      await deleteSchedule(p.schedule_id as number);
      return null;
    case 'commitment_status':
      await bulkUpdateCommitments(
        [p.commitment_id as number],
        p.to_status as 'confirmed' | 'fulfilled' | 'dismissed',
      );
      return null;
  }
}

/** 방금 한 일을 되돌린다. safe 액션에만 붙는다 — confirm 액션은 애초에
 * 되돌릴 수 없어서 승인을 받는 것이다. */
async function undo(action: AssistantAction, createdId: number | null): Promise<void> {
  switch (action.kind) {
    case 'todo_add':
      if (createdId !== null) await deleteTodo(createdId);
      return;
    case 'todo_done':
      await updateTodo(action.payload.todo_id as number, { is_done: false });
      return;
    case 'schedule_add':
      if (createdId !== null) await deleteSchedule(createdId);
      return;
    default:
      return;
  }
}

export function AssistantActionCard({
  action,
  groupId,
  createdId = null,
  onChanged,
}: {
  action: AssistantAction;
  groupId: number;
  /** safe 액션은 AssistantPanel이 응답 직후 이미 실행했다. 그때 만들어진 id. */
  createdId?: number | null;
  onChanged: () => void;
}) {
  const [state, setState] = useState<State>(action.risk === 'safe' ? 'applied' : 'idle');
  const [madeId, setMadeId] = useState<number | null>(createdId);
  const [failure, setFailure] = useState<string | null>(null);

  const run = async () => {
    setState('running');
    setFailure(null);
    try {
      setMadeId(await applySafeAction(action, groupId));
      setState('applied');
      onChanged();
    } catch (err) {
      setState('failed');
      setFailure(err instanceof Error ? err.message : '실행하지 못했습니다.');
    }
  };

  const rollback = async () => {
    setState('running');
    setFailure(null);
    try {
      await undo(action, madeId);
      setState('declined');
      onChanged();
    } catch (err) {
      setState('failed');
      setFailure(err instanceof Error ? err.message : '되돌리지 못했습니다.');
    }
  };

  return (
    <div className="rounded-lg border border-border bg-foreground/[0.02] px-3 py-2">
      <p className="text-xs font-bold leading-relaxed text-foreground">{action.label}</p>

      {action.kind === 'commitment_status' && (
        <p className="mt-1 border-l-2 border-border pl-2 text-xs italic leading-relaxed text-foreground/70">
          {String(action.payload.content ?? '')}
          {action.payload.client_name ? ` — ${String(action.payload.client_name)}` : ''}
        </p>
      )}

      {action.warning && state !== 'declined' && (
        <p className="mt-1 font-mono text-[10px] text-amber-400">{action.warning}</p>
      )}

      {failure && (
        <p role="alert" className="mt-1 text-[10px] leading-relaxed text-red-300">
          {failure}
        </p>
      )}

      <div className="mt-2 flex gap-2">
        {state === 'idle' && (
          <>
            <button
              type="button"
              onClick={run}
              className="rounded border border-accent/40 px-2 py-1 text-[10px] font-bold text-accent transition hover:bg-accent/[0.12]"
            >
              그렇게 해
            </button>
            <button
              type="button"
              onClick={() => setState('declined')}
              className="rounded border border-border px-2 py-1 text-[10px] text-foreground/60 transition hover:bg-foreground/[0.04]"
            >
              아니
            </button>
          </>
        )}

        {state === 'running' && <span className="text-[10px] text-foreground/40">처리 중…</span>}

        {state === 'applied' && (
          <>
            <span className="text-[10px] text-foreground/50">적용됨</span>
            {action.risk === 'safe' && (
              <button
                type="button"
                onClick={rollback}
                className="rounded border border-border px-2 py-1 text-[10px] text-foreground/60 transition hover:bg-foreground/[0.04]"
              >
                취소
              </button>
            )}
          </>
        )}

        {state === 'declined' && <span className="text-[10px] text-foreground/40">하지 않음</span>}

        {state === 'failed' && (
          <button
            type="button"
            onClick={run}
            className="rounded border border-border px-2 py-1 text-[10px] text-foreground/60 transition hover:bg-foreground/[0.04]"
          >
            다시 시도
          </button>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: `AssistantPanel.tsx`에 배선한다**

import를 추가:

```tsx
import { AssistantActionCard, applySafeAction } from '@/components/AssistantActionCard';
```

`Message` 타입에 실행 결과 id를 담을 칸을 넣는다:

```tsx
type Message = {
  role: 'user' | 'assistant';
  content: string;
  actions: AssistantAction[];
  /** safe 액션을 응답 직후 실행하며 만들어진 id. 취소할 때 쓴다. */
  createdIds: Record<string, number | null>;
};
```

기존 `setMessages` 두 곳에 `createdIds: {}`를 채운다(사용자 메시지, 그리고 아래 비서 메시지).

`useWorkspace()` 구조분해에 `refresh`를 추가:

```tsx
  const { currentGroupId, refresh } = useWorkspace();
```

`send`에서 응답을 받은 뒤 비서 메시지를 넣기 **전에** safe 액션을 실행한다:

```tsx
      const reply = await sendAssistantMessage(currentGroupId, text, history);

      // safe 액션은 물어보지 않고 바로 실행한다. 되돌릴 수 있는 것만 여기 온다.
      const createdIds: Record<string, number | null> = {};
      for (const action of reply.actions) {
        if (action.risk !== 'safe') continue;
        try {
          createdIds[action.id] = await applySafeAction(action, currentGroupId);
        } catch {
          // 실패해도 대화는 이어간다. 카드가 '다시 시도'를 보여준다.
        }
      }
      if (reply.actions.some((a) => a.risk === 'safe')) refresh();

      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: reply.reply, actions: reply.actions, createdIds },
      ]);
```

메시지 렌더 안, 말풍선 `<p>` 아래에 카드를 그린다:

```tsx
            {m.actions.length > 0 && (
              <div className="mt-2 space-y-2 text-left">
                {m.actions.map((a) => (
                  <AssistantActionCard
                    key={a.id}
                    action={a}
                    groupId={currentGroupId}
                    createdId={m.createdIds[a.id] ?? null}
                    onChanged={refresh}
                  />
                ))}
              </div>
            )}
```

- [ ] **Step 3: 타입 검사**

Run: `cd onque-frontend && npx tsc --noEmit`
Expected: 에러 0건

- [ ] **Step 4: 빌드**

Run: `cd onque-frontend && npx next build --webpack`
Expected: 성공

- [ ] **Step 5: 커밋**

```bash
git add onque-frontend/components/AssistantActionCard.tsx onque-frontend/components/AssistantPanel.tsx
git commit -m "feat: 비서 액션 카드와 실행

kind로 고정 분기해 기존 API 래퍼를 부른다. 서버 응답에 URL이 없어
모델 출력이 요청 경로에 닿지 않는다.

safe는 즉시 실행 후 취소 버튼, confirm은 승인 후 실행. 약속 전이는
역방향이 없어 전부 confirm이다."
```

---

### Task 8: 패널 재구성 — 접힌 요약

**Files:**
- Modify: `onque-frontend/components/SmartDashboardPanel.tsx`

**Interfaces:**
- Consumes: `useWorkspace()`의 `todos`, `schedules`, `proposedCount`, `dueSoon`; Task 6의 `<AssistantPanel />`
- Produces: 없음 (최종 화면)

**회귀 위험이 가장 큰 태스크다.** 펼친 상태에서 기존 할 일·일정의 체크와 삭제가 그대로 동작해야 한다. **섹션 내부 마크업을 한 글자도 바꾸지 않는다** — 감싸기만 한다.

- [ ] **Step 1: 접힘 상태를 추가한다**

`useState`가 이미 import돼 있다. `useElapsedLabel` 호출 아래에:

```tsx
  const [expanded, setExpanded] = useState(false);
```

- [ ] **Step 2: 요약 헤더를 넣고 기존 세 섹션을 감싼다**

에러 배너 아래, 기존 약속 섹션 위에 헤더를 넣는다:

```tsx
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className="flex w-full items-center justify-between border-b border-border px-5 py-3 text-left transition hover:bg-foreground/[0.03]"
      >
        <span className="font-mono text-[10px] text-foreground/60">
          할 일 {openTodos.length} · 일정 {schedules.length}
          {(proposedCount > 0 || dueSoon.length > 0) &&
            ` · 확인 필요 ${proposedCount} · 기한 주의 ${dueSoon.length}`}
        </span>
        <span className="font-mono text-[10px] text-foreground/40">
          {expanded ? '접기' : '펼치기'}
        </span>
      </button>
```

그리고 기존 **약속 섹션 · 할 일 섹션 · 일정 섹션 세 덩어리 전체**를 이 컨테이너로 감싼다:

```tsx
      {expanded && (
        <div className="max-h-[45%] shrink-0 overflow-y-auto">
          {/* 기존 약속 섹션 — 내용 그대로 */}
          {/* 기존 할 일 섹션 — 내용 그대로 */}
          {/* 기존 일정 섹션 — 내용 그대로 */}
        </div>
      )}
```

- [ ] **Step 3: `aside`가 비서에게 남는 높이를 주도록 고친다**

`aside`의 className에서 `overflow-y-auto`를 `overflow-hidden`으로 바꾼다. 스크롤은 펼침 컨테이너와 `AssistantPanel`이 각자 한다.

```tsx
    <aside className="hidden w-[320px] shrink-0 flex-col overflow-hidden border-l border-border bg-surface lg:flex xl:w-[360px]">
```

`AssistantPanel`은 이미 `flex min-h-0 flex-1`이라 남은 높이를 채운다.

- [ ] **Step 4: 타입 검사**

Run: `cd onque-frontend && npx tsc --noEmit`
Expected: 에러 0건

- [ ] **Step 5: 빌드**

Run: `cd onque-frontend && npx next build --webpack`
Expected: 성공

- [ ] **Step 6: 백엔드 회귀 확인**

Run: `./venv/bin/python -m pytest -q`
Expected: 223 passed (프론트 전용 태스크라 변동이 없어야 한다)

- [ ] **Step 7: 커밋**

```bash
git add onque-frontend/components/SmartDashboardPanel.tsx
git commit -m "refactor: 우측 패널 목록을 접고 비서에 자리를 내준다

목록은 숫자로 접히고 펼치면 그대로 나온다 — 체크와 삭제를 잃지 않는다.
대시보드 페이지에 같은 목록이 이미 있어 상시 노출의 값어치가 낮았다."
```

---

## 리뷰 지시문에 반드시 넣을 것

- **그룹 격리** — 컨텍스트와 액션 검증 양쪽에서 타 그룹 데이터가 새지 않는지. 이 브랜치 최대 보안 위험
- **비서 엔드포인트가 DB를 쓰지 않는지** — `db.commit()`/`add()`/`delete()` 검색
- **Task 8 회귀** — 펼쳤을 때 체크박스·삭제가 그대로 동작하는지, 목록이 길 때 입력창이 화면 밖으로 밀리지 않는지
- **기존 `/chat` 봇을 안 건드렸는지** — `generate_bot_reply`, `extract_chat_actions` 무변경
- TS-025: 테스트를 지우거나 다시 썼다면 커버리지 회계

## 자기점검 결과

**스펙 커버리지**

| 스펙 요구 | 태스크 |
|---|---|
| 컨텍스트 수집·상한·정렬·전사 일정 | Task 1 |
| 프롬프트 규칙, 환각 방지, 실패 시 None | Task 2 |
| 액션 검증(없는 id·타 그룹·불법 전이) | Task 3 |
| 위험 분류(safe/confirm)와 경고 문구 | Task 3 |
| 엔드포인트, 권한 403, history 상한, 502, 422 | Task 4 |
| 비서 엔드포인트가 DB를 안 쓴다 | Task 3·4 테스트 |
| 버린 액션을 답변에 밝힌다 | Task 4 |
| `createSchedule` 래퍼 신설 | Task 5 |
| 대화 UI, 실패 시 문장 보존, 그룹 전환 초기화 | Task 6 |
| 액션 카드, safe 즉시 실행 + 취소, confirm 승인 | Task 7 |
| 접힌 요약 + 펼치면 기존 목록 | Task 8 |

스펙 검증 기준 9개: 1·2는 Task 2 프롬프트, 3은 Task 7, 4·5는 Task 3·7, 6은 Task 6, 7은 Task 8, 8은 Task 4·6, 9는 Task 1·6이 담당한다. 빠진 요구 없음.

**타입 일관성**

- `AssistantAction` 필드(`id`·`risk`·`kind`·`label`·`warning`·`payload`)가 Task 3 `_action()` 반환, Task 5 타입, Task 7 소비에서 일치
- `answer_assistant(context_text, history, message)` 시그니처가 Task 2 정의·Task 4 호출·Task 4 테스트 목에서 동일
- `validate_actions(db, group_id, raw_actions) -> (list, int)` 가 Task 3 정의와 Task 4 호출에서 동일
- `applySafeAction(action, groupId) -> Promise<number|null>` 가 Task 7 안에서 정의·소비 일치
- `HISTORY_MESSAGE_LIMIT`은 Task 1에서 정의하고 Task 4에서만 쓴다

**남은 위험**

- Task 8이 `aside`의 스크롤 구조를 바꾼다. 목록이 길 때 비서 입력창이 밀리지 않는지 리뷰에서 확인해야 한다
- Task 7의 `applySafeAction`이 컴포넌트 파일에서 export된다. 리뷰어가 분리를 요구하면 `lib/assistant-actions.ts`로 옮긴다
- `POST /todos`·`POST /schedules`는 `main.py` 라우트라 봉투가 없다. Task 5·7에서 `request`/`requestEnveloped`를 섞어 쓰면 런타임에 `undefined`가 된다
