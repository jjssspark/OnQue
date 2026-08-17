# AI 호출 예산 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gemini 무료 티어 하루 20건을 스윕·요약·비서·채팅이 나눠 쓰게 하고, 중복 호출을 없애 사용자 몫의 유효 용량을 두 배로 늘린다.

**Architecture:** 전역 일일 장부(`call_budget`) 하나에 총 사용량만 기록하고, 소비자별 상한을 다르게 둔다(예비선 방식). `gemini_service`의 모든 호출 함수가 `claim`을 **필수 인자**로 받게 해 예산 우회를 문법적으로 불가능하게 만든다. 차감은 요청 트랜잭션과 분리된 세션에서 즉시 커밋한다.

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy 2.x / Postgres(Neon, 테스트는 SQLite 인메모리) / pytest — 프론트는 Next.js 16 / React 19 / vitest

**Spec:** `docs/superpowers/specs/2026-08-17-ai-call-budget-design.md`

## Global Constraints

- 배분 규칙: `user`는 `calls < DAILY_TOTAL`, `sweep`은 `calls < DAILY_TOTAL - RESERVE`. 기본값 `DAILY_TOTAL=20`, `RESERVE=12` (→ 스윕 상한 8건).
- 모든 설정값은 환경변수로 덮어쓸 수 있어야 한다. 이름은 `AI_DAILY_TOTAL`, `AI_BUDGET_RESERVE`.
- 소진 응답은 HTTP 429 + `error.code = "AI_DAILY_BUDGET_EXHAUSTED"` 로 전 경로 통일.
- 선차감을 유지한다. 호출 실패 시 장부를 되돌리지 않는다.
- 날짜/시각은 ISO 8601 UTC 문자열. 장부의 하루 경계는 UTC 자정.
- 새 파일은 800줄을 넘기지 않는다. 주석은 WHY가 명확하지 않을 때만 쓴다.
- **테스트 환경 주의**: `tests/conftest.py:25`가 `db.engine`만 교체하고 `db.SessionLocal`(`db.py:19`)은 import 시점에 원래 엔진에 바인딩돼 있다. 별도 세션은 반드시 **호출 시점에** `Session(bind=db.engine)`으로 열어야 테스트 엔진을 집는다.
- 커밋 메시지는 한국어. 각 태스크 끝에서 커밋한다.

---

### Task 1: `call_budget` 모듈과 테이블 개명

`sweep_budget` 테이블을 `call_budget`으로 개명하고, 예비선 규칙을 담은 모듈을 만든다. 선점 로직은 `commitment_service._claim_sweep_call`에서 가져오되 상한만 소비자별로 달라진다.

**Files:**
- Create: `call_budget.py`
- Create: `tests/test_call_budget.py`
- Create: `scripts/migrate_rename_sweep_budget.py`
- Modify: `models.py:293-310` (`SweepBudget` → `CallBudget`)

**Interfaces:**
- Consumes: `db.Base`, `db.engine`, `models.CallBudget`
- Produces:
  - `call_budget.DAILY_TOTAL: int`, `call_budget.RESERVE: int`
  - `call_budget.claim(db: Session, consumer: str) -> bool` — `consumer`는 `"user"` 또는 `"sweep"`
  - `call_budget.remaining(db: Session) -> int`
  - `call_budget.used_today(db: Session) -> int`
  - `call_budget.resets_at() -> datetime` — 다음 UTC 자정 (tz-aware)
  - `call_budget.user_claimer() -> Callable[[], bool]` — 부르면 별도 세션으로 `"user"` 1건 선점
  - `call_budget.sweep_claimer() -> Callable[[], bool]` — 같은 것의 `"sweep"` 판
  - `models.CallBudget` (`__tablename__ = "call_budget"`, 컬럼 `day: date` PK, `calls: int`)

- [ ] **Step 1: 모델을 개명한다**

`models.py:293-310`의 `class SweepBudget(Base):` 블록 전체를 아래로 교체한다.

```python
class CallBudget(Base):
    """하루에 쓴 Gemini 호출 수. 하루 한 행.

    스윕만 세던 장부를 전체 소비로 넓혔다. 사용자가 직접 부르는 요약·비서·채팅이
    장부에 안 잡히면, 배경 작업만 아껴봐야 한도는 그대로 소진된다.

    그룹이 아니라 전역이다 — Gemini 한도는 API 키 하나에 걸리므로 그룹마다
    예산을 주면 그룹 수만큼 한도를 넘긴다.

    소비자별로 나눠 세지 않는다. 배분은 상한 규칙으로 하고(call_budget.claim),
    누가 얼마나 썼는지는 구조화 로그로 남긴다. 컬럼을 늘리면 소비자가 생길
    때마다 스키마가 바뀐다.

    날짜는 UTC 기준이다. 코드베이스가 전부 UTC로 저장·비교한다.
    """

    __tablename__ = "call_budget"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    calls: Mapped[int] = mapped_column(nullable=False, server_default="0")
```

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`tests/test_call_budget.py`를 새로 만든다.

```python
from datetime import date, datetime, timedelta, timezone

import pytest

import call_budget
from models import CallBudget


def _set_used(db_session, calls, day=None):
    """오늘 장부를 특정 값으로 만들어 둔다."""
    db_session.merge(CallBudget(day=day or datetime.now(timezone.utc).date(), calls=calls))
    db_session.commit()


def test_user는_잔량이_있으면_쓴다(client, db_session, monkeypatch):
    monkeypatch.setattr(call_budget, "DAILY_TOTAL", 20)
    monkeypatch.setattr(call_budget, "RESERVE", 12)
    _set_used(db_session, 19)

    assert call_budget.claim(db_session, "user") is True
    assert call_budget.used_today(db_session) == 20


def test_user는_총량에_도달하면_막힌다(client, db_session, monkeypatch):
    monkeypatch.setattr(call_budget, "DAILY_TOTAL", 20)
    monkeypatch.setattr(call_budget, "RESERVE", 12)
    _set_used(db_session, 20)

    assert call_budget.claim(db_session, "user") is False
    assert call_budget.used_today(db_session) == 20


def test_sweep은_예비선에서_멈춘다(client, db_session, monkeypatch):
    """총량 20 - 예비선 12 = 스윕 상한 8. 8건을 쓴 뒤로는 잔량 12가
    남아 있어도 스윕은 못 쓴다 — 그 12는 사용자 몫이다."""
    monkeypatch.setattr(call_budget, "DAILY_TOTAL", 20)
    monkeypatch.setattr(call_budget, "RESERVE", 12)
    _set_used(db_session, 7)

    assert call_budget.claim(db_session, "sweep") is True   # 7 -> 8
    assert call_budget.claim(db_session, "sweep") is False  # 상한 도달
    assert call_budget.used_today(db_session) == 8
    # 사용자는 같은 자리에서 계속 쓸 수 있다
    assert call_budget.claim(db_session, "user") is True


def test_장부가_없으면_첫_선점이_행을_만든다(client, db_session, monkeypatch):
    monkeypatch.setattr(call_budget, "DAILY_TOTAL", 20)
    monkeypatch.setattr(call_budget, "RESERVE", 12)

    assert call_budget.used_today(db_session) == 0
    assert call_budget.claim(db_session, "user") is True
    assert call_budget.used_today(db_session) == 1


def test_어제_장부는_오늘에_영향을_주지_않는다(client, db_session, monkeypatch):
    monkeypatch.setattr(call_budget, "DAILY_TOTAL", 20)
    monkeypatch.setattr(call_budget, "RESERVE", 12)
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    _set_used(db_session, 20, day=yesterday)

    assert call_budget.used_today(db_session) == 0
    assert call_budget.claim(db_session, "user") is True


def test_총량_0이면_아무도_못_쓴다(client, db_session, monkeypatch):
    """운영 중 급히 AI를 끌 때 쓰는 스위치다. 0인데 행을 만들어
    1을 넣어버리면 스위치가 안 먹는다."""
    monkeypatch.setattr(call_budget, "DAILY_TOTAL", 0)
    monkeypatch.setattr(call_budget, "RESERVE", 0)

    assert call_budget.claim(db_session, "user") is False
    assert call_budget.claim(db_session, "sweep") is False
    assert call_budget.used_today(db_session) == 0


def test_remaining은_남은_수를_돌려준다(client, db_session, monkeypatch):
    monkeypatch.setattr(call_budget, "DAILY_TOTAL", 20)
    _set_used(db_session, 13)

    assert call_budget.remaining(db_session) == 7


def test_remaining은_음수로_내려가지_않는다(client, db_session, monkeypatch):
    """설정을 낮춰 잡은 뒤라면 used가 총량을 넘을 수 있다.
    화면이 '-3건 남음'을 그리게 두지 않는다."""
    monkeypatch.setattr(call_budget, "DAILY_TOTAL", 10)
    _set_used(db_session, 13)

    assert call_budget.remaining(db_session) == 0


def test_모르는_소비자는_거부한다(client, db_session):
    """오타 난 소비자 이름이 조용히 통과하면 예산 밖에서 호출이 나간다."""
    with pytest.raises(ValueError):
        call_budget.claim(db_session, "assistant")


def test_resets_at은_다음_UTC_자정이다(client):
    resets = call_budget.resets_at()

    assert resets.tzinfo is not None
    assert (resets.hour, resets.minute, resets.second) == (0, 0, 0)
    assert resets > datetime.now(timezone.utc)
    assert resets.date() == datetime.now(timezone.utc).date() + timedelta(days=1)


def test_claimer는_자기_세션으로_차감한다(client, db_session, monkeypatch):
    """호출부의 트랜잭션과 분리돼야 한다. 바깥이 롤백해도 차감은 남는다."""
    monkeypatch.setattr(call_budget, "DAILY_TOTAL", 20)
    monkeypatch.setattr(call_budget, "RESERVE", 12)

    claimer = call_budget.user_claimer()
    assert claimer() is True

    fresh = call_budget.used_today(db_session)
    assert fresh == 1
```

**설계의 테스트 항목 하나는 이 환경에서 검증할 수 없다.** 설계 문서는 "차감이 바깥
트랜잭션 롤백에 영향받지 않음"을 확인하라고 적었지만, `tests/conftest.py:14-18`의
SQLite 인메모리 + `StaticPool`은 **모든 세션이 커넥션 하나를 공유**한다. 별도 세션을
열어도 실제로는 같은 트랜잭션이라, 격리를 확인하려는 테스트가 통과해도 통과한
이유가 다르고 실패해도 프로덕션(Postgres) 동작과 무관하다.

그래서 그 항목은 테스트로 만들지 않는다. 위 `test_claimer는_자기_세션으로_차감한다`가
확인하는 것은 "claimer가 호출부 세션을 쓰지 않고 자기 세션을 연다"까지다. 진짜 격리는
Task 7 Step 4의 브라우저 확인에서 실제 Postgres로 보고, 어긋나면 그때 잡는다.
**이 한계를 모른 채 초록을 보고 안심하지 않도록 여기 적어둔다.**

- [ ] **Step 3: 테스트가 실패하는지 확인한다**

Run: `./venv/bin/python -m pytest tests/test_call_budget.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'call_budget'`

- [ ] **Step 4: 모듈을 구현한다**

`call_budget.py`를 새로 만든다.

```python
"""Gemini 호출의 하루 예산 장부.

무료 티어는 하루 20건이고, 그 한도를 백그라운드 스윕과 사용자가 직접 부르는
요약·비서·채팅이 함께 쓴다. 장부가 없으면 오전 채팅이 한도를 다 먹고, 오후에
회의 녹음을 올린 사람이 소진을 만난다 — 시킨 일이 안 시킨 일 때문에 실패한다.

배분은 예비선 방식이다. 총량 하나만 세고 소비자별로 상한을 다르게 둔다.
사용자는 잔량이 있으면 끝까지 쓰고, 스윕은 예비선 위에서만 돈다.
장부를 둘로 나누지 않은 이유: 스윕이 3건만 쓴 날에도 사용자가 12에서
막히기 때문이다.
"""

import os
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import db as db_module
from models import CallBudget

DAILY_TOTAL = int(os.getenv("AI_DAILY_TOTAL", "20"))
# 사용자 몫으로 떼어두는 양. 스윕은 이 선 위에서만 돈다.
RESERVE = int(os.getenv("AI_BUDGET_RESERVE", "12"))

_CONSUMERS = ("user", "sweep")


def _ceiling(consumer: str) -> int:
    """이 소비자가 넘을 수 없는 누적 호출 수."""
    if consumer not in _CONSUMERS:
        # 조용히 통과시키면 예산 밖에서 호출이 나간다.
        raise ValueError(f"알 수 없는 소비자: {consumer}")
    return DAILY_TOTAL if consumer == "user" else DAILY_TOTAL - RESERVE


def _today() -> date:
    return datetime.now(timezone.utc).date()


def used_today(db: Session) -> int:
    """오늘 쓴 호출 수. 장부가 아직 없으면 0."""
    used = db.execute(
        select(CallBudget.calls).where(CallBudget.day == _today())
    ).scalar_one_or_none()
    return used or 0


def remaining(db: Session) -> int:
    """남은 호출 수. 설정을 낮춰 잡은 뒤라면 음수가 될 수 있어 0에서 자른다."""
    return max(0, DAILY_TOTAL - used_today(db))


def resets_at() -> datetime:
    """장부가 초기화되는 시각 = 다음 UTC 자정.

    Gemini 실제 리셋 시각이 UTC 자정인지는 검증하지 않았다(설계 문서의
    미해결 항목). 여기서 돌려주는 값은 '우리 장부'의 초기화 시각이다.
    """
    return datetime.combine(_today() + timedelta(days=1), time.min, tzinfo=timezone.utc)


def claim(db: Session, consumer: str) -> bool:
    """오늘치 예산에서 호출 1건을 선점한다. 남아 있으면 True.

    조건부 UPDATE의 rowcount로 판정한다. SELECT 후 UPDATE 하면 두 요청이 같은
    잔량을 읽고 둘 다 통과해 예산을 넘긴다.

    오늘 행이 아직 없으면 UPDATE가 0건이라 삽입해야 하는데, 이때 다른 요청이
    먼저 넣었으면 IntegrityError가 난다. 그대로 두면 바깥 트랜잭션까지
    오염되므로 SAVEPOINT 안에서 시도하고, 졌으면 UPDATE로 재시도한다.

    선점에 성공하면 곧바로 커밋한다. 이 뒤 Gemini 호출이 실패해 호출자가
    rollback 하더라도 차감분은 남아야 한다 — 호출은 이미 나가서 실제 한도는
    깎였는데 장부만 복구되면, 실패하는 경로 하나가 남은 예산을 전부 태우며
    재시도를 반복한다.
    """
    ceiling = _ceiling(consumer)
    if ceiling < 1:
        return False

    today = _today()
    bumped = db.execute(
        update(CallBudget)
        .where(CallBudget.day == today, CallBudget.calls < ceiling)
        .values(calls=CallBudget.calls + 1)
        .execution_options(synchronize_session=False)
    )
    if bumped.rowcount == 1:
        db.commit()
        return True

    # 행이 있는데 못 올렸다면 상한 도달이다. 삽입을 시도하면 안 된다.
    if db.execute(
        select(CallBudget.day).where(CallBudget.day == today)
    ).scalar_one_or_none() is not None:
        return False

    try:
        with db.begin_nested():
            db.execute(insert(CallBudget).values(day=today, calls=1))
        db.commit()
        return True
    except IntegrityError:
        # 다른 요청이 먼저 오늘 행을 만들었다. 그 행 위에서 다시 겨룬다.
        retried = db.execute(
            update(CallBudget)
            .where(CallBudget.day == today, CallBudget.calls < ceiling)
            .values(calls=CallBudget.calls + 1)
            .execution_options(synchronize_session=False)
        )
        if retried.rowcount == 1:
            db.commit()
            return True
        return False


def _claimer(consumer: str) -> Callable[[], bool]:
    """부르면 자기 세션을 열어 1건 선점하고 닫는 호출 가능 객체.

    요청 트랜잭션과 분리하는 이유는 claim의 주석과 같다 — 장부는 바깥
    트랜잭션의 성패를 따라가면 안 된다. 채팅 메시지 POST 같은 쓰기 트랜잭션
    한가운데서 같은 세션에 커밋하면, 아직 완성되지 않은 상태까지 함께 커밋된다.

    엔진을 import 시점이 아니라 호출 시점에 읽는다. tests/conftest.py가
    db.engine만 갈아끼우기 때문에, 여기서 db_module.SessionLocal을 쓰면
    테스트가 실제 DATABASE_URL로 접속하려 든다.
    """

    def run() -> bool:
        session = Session(bind=db_module.engine)
        try:
            return claim(session, consumer)
        finally:
            session.close()

    return run


def user_claimer() -> Callable[[], bool]:
    return _claimer("user")


def sweep_claimer() -> Callable[[], bool]:
    return _claimer("sweep")
```

- [ ] **Step 5: 테스트가 통과하는지 확인한다**

Run: `./venv/bin/python -m pytest tests/test_call_budget.py -v`
Expected: PASS (11 tests)

- [ ] **Step 6: 기존 참조가 깨지지 않았는지 확인한다**

Run: `./venv/bin/python -m pytest -q 2>&1 | tail -20`

`models.SweepBudget`을 import 하던 `commitment_service.py`가 깨진다. Task 4에서 걷어내기 전이므로, `commitment_service.py`의 `from models import ... SweepBudget` 을 `CallBudget`으로 바꾸고 `_claim_sweep_call`·`sweep_calls_used_today` 안의 `SweepBudget`을 `CallBudget`으로 치환해 초록으로 되돌린다. 로직은 건드리지 않는다 — 이 함수들은 Task 4에서 통째로 사라진다.

Expected: 291 passed (기존 280 + 신규 11)

- [ ] **Step 7: 마이그레이션 스크립트를 쓴다**

`scripts/migrate_rename_sweep_budget.py`를 만든다.

```python
"""sweep_budget 테이블을 call_budget으로 개명한다.

장부의 의미가 "스윕이 쓴 수"에서 "전체 소비"로 넓어졌다. 이름을 두면
거짓말이 되고, 나중에 읽는 사람이 사용자 호출은 안 세는 줄 안다.

행 구조는 그대로다(day PK, calls). 개명만 하므로 데이터 손실이 없다.
되돌리려면 반대 방향으로 ALTER 하면 된다.

이미 call_budget이 있으면(재실행) 아무것도 하지 않는다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, text  # noqa: E402

from db import Base, engine  # noqa: E402
import models  # noqa: E402,F401  ─ create_all이 테이블을 알려면 import가 필요하다

with engine.begin() as conn:
    tables = set(inspect(conn).get_table_names())

    if "call_budget" in tables:
        action = "이미 개명됨"
    elif "sweep_budget" in tables:
        conn.execute(text("ALTER TABLE sweep_budget RENAME TO call_budget"))
        action = "sweep_budget -> call_budget"
    else:
        action = "둘 다 없음 — create_all이 새로 만든다"

# 개명 후(또는 둘 다 없을 때) 누락 테이블을 채운다.
Base.metadata.create_all(bind=engine)

with engine.begin() as conn:
    after = set(inspect(conn).get_table_names())
    rows = conn.execute(text("SELECT count(*) FROM call_budget")).scalar()

print(action)
print(f"call_budget 행: {rows}")

assert "call_budget" in after, "call_budget 테이블이 없다"
assert "sweep_budget" not in after, "sweep_budget이 남아 있다"
```

- [ ] **Step 8: 커밋한다**

```bash
git add call_budget.py tests/test_call_budget.py scripts/migrate_rename_sweep_budget.py models.py commitment_service.py
git commit -m "feat: 전역 AI 호출 예산 장부와 예비선 배분 규칙

sweep_budget을 call_budget으로 넓혀 전체 소비를 센다. 사용자는 잔량이
있으면 끝까지 쓰고, 스윕은 예비선(12) 위에서만 돈다."
```

---

### Task 2: `/문서`의 중복 분류 호출 제거

`main.py:1021`이 이미 받아온 `structured["category"]`를 버리고 `classify_document_category`를 무조건 다시 부른다. 업로드 경로(`main.py:218`)는 이미 폴백으로만 부르도록 고쳐져 있다 — 같은 수정을 빠진 곳에 적용한다.

**Files:**
- Modify: `main.py:1017-1025`
- Test: `tests/test_chat_commands.py`

**Interfaces:**
- Consumes: 없음 (Task 1과 독립)
- Produces: 없음 (동작 변경만)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_chat_commands.py` 끝에 추가한다. 기존 헬퍼 `_setup`, `_say`를 그대로 쓴다.

```python
def test_문서_명령은_초안에_분류가_있으면_모델을_다시_부르지_않는다(client, monkeypatch):
    """초안 응답 스키마(_SUMMARY_SCHEMA)에 category가 이미 들어 있다.
    한 번 더 묻는 건 하루 20건짜리 한도에서 순수 낭비다."""
    auth, _, room_id = _setup(client)
    _say(client, auth, room_id, "/help")

    structured = {
        "headline": "출시일 확정",
        "key_points": ["8월 30일 출시"],
        "requests": [],
        "action_items": [],
        "notes": "",
        "commitments": [],
        "category": "기획",
    }
    monkeypatch.setattr(
        gemini_service, "draft_document_from_conversation", lambda msgs, title: structured
    )

    def must_not_be_called(text):
        raise AssertionError("초안에 분류가 있는데 classify_document_category를 불렀다")

    monkeypatch.setattr(gemini_service, "classify_document_category", must_not_be_called)

    result = _say(client, auth, room_id, "/문서 회의록")
    assert result.status_code == 200


def test_문서_명령은_초안에_분류가_없을_때만_분류를_부른다(client, monkeypatch):
    auth, _, room_id = _setup(client)
    _say(client, auth, room_id, "/help")

    structured = {
        "headline": "출시일 확정",
        "key_points": ["8월 30일 출시"],
        "requests": [],
        "action_items": [],
        "notes": "",
        "commitments": [],
        "category": "",
    }
    monkeypatch.setattr(
        gemini_service, "draft_document_from_conversation", lambda msgs, title: structured
    )
    called = []
    monkeypatch.setattr(
        gemini_service,
        "classify_document_category",
        lambda text: called.append(text) or "기타",
    )

    result = _say(client, auth, room_id, "/문서 회의록")
    assert result.status_code == 200
    assert len(called) == 1
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `./venv/bin/python -m pytest tests/test_chat_commands.py -k "문서_명령은" -v`
Expected: 첫 번째가 FAIL — `AssertionError: 초안에 분류가 있는데 classify_document_category를 불렀다`

- [ ] **Step 3: 구현한다**

`main.py:1021`의 한 줄을 바꾼다. 변경 전:

```python
            category=gemini_service.classify_document_category(summary_text),
```

변경 후:

```python
            # 분류는 초안 응답에 함께 온다(_SUMMARY_SCHEMA에 category가 있다).
            # 업로드 경로와 같은 폴백 형태다 — 구조화 파싱이 category를 못
            # 채웠을 때만 모델을 한 번 더 부른다.
            category=structured.get("category")
            or gemini_service.classify_document_category(summary_text),
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `./venv/bin/python -m pytest tests/test_chat_commands.py -v`
Expected: PASS (기존 + 신규 2건)

- [ ] **Step 5: 커밋한다**

```bash
git add main.py tests/test_chat_commands.py
git commit -m "fix: /문서가 이미 받은 분류를 버리고 모델을 다시 부르던 것

업로드 경로에만 적용돼 있던 폴백 형태를 채팅 문서화 경로에도 적용한다.
호출이 2건에서 1건으로 준다."
```

---

### Task 3: 채팅 두 호출을 하나로 병합

`extract_chat_actions` + `generate_bot_reply`를 `chat_reply_with_actions` 하나로 합친다. `answer_assistant`가 이미 쓰는 구조(한 응답에 `reply` + 액션)를 따른다. 기존 두 함수는 **지우지 않는다** — `/할일`·`/질문`이 각각 쓰고 있고, 품질이 나빠지면 호출부 한 줄로 되돌리기 위해서다.

**Files:**
- Modify: `gemini_service.py` (`extract_chat_actions` 아래에 스키마·프롬프트·함수 추가)
- Modify: `main.py:1083-1089`
- Test: `tests/test_chat_commands.py`

**Interfaces:**
- Consumes: `gemini_service._EXTRACTION_SCHEMA`, `_EMPTY_EXTRACTION`, `korean_date_context()`, `_format_history()`
- Produces:
  - `gemini_service.chat_reply_with_actions(recent_messages: list[dict], message: str) -> dict`
    — 돌려주는 dict는 `_EMPTY_EXTRACTION`의 모든 키 + `"reply": str`.
      실패 시 `{**_EMPTY_EXTRACTION, "reply": ""}`.
    - **주의**: Task 4에서 이 시그니처 끝에 `*, claim: Callable[[], bool]` 이 붙는다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_chat_commands.py`에 추가한다.

```python
def test_병합_호출은_답변과_액션을_한_번에_돌려준다(monkeypatch):
    """모델을 두 번 부르지 않고 한 응답에서 둘 다 받는다."""
    import json

    class FakeResponse:
        text = json.dumps(
            {
                "reply": "네, 내일까지 견적서 확인하겠습니다.",
                "add_todos": [{"content": "견적서 보내기", "due_date": "2026-08-18"}],
                "complete_todo_hints": [],
                "delete_todo_hints": [],
                "add_schedules": [],
                "delete_schedule_hints": [],
            }
        )

    calls = []

    def fake_generate(**kwargs):
        calls.append(kwargs)
        return FakeResponse()

    monkeypatch.setattr(gemini_service.client.models, "generate_content", fake_generate)

    result = gemini_service.chat_reply_with_actions(
        [{"sender": "김대리", "content": "안녕하세요"}], "내일까지 견적서 보낼게요"
    )

    assert len(calls) == 1
    assert result["reply"] == "네, 내일까지 견적서 확인하겠습니다."
    assert result["add_todos"] == [{"content": "견적서 보내기", "due_date": "2026-08-18"}]
    assert result["complete_todo_hints"] == []


def test_병합_호출이_실패하면_답변도_액션도_없다(monkeypatch):
    """합친 대가다. 지금은 추출이 실패해도 답변은 나갔지만, 한 번에
    받으므로 한 번의 실패가 둘 다 잃는다. 대신 호출은 1건만 태운다."""

    def boom(**kwargs):
        raise RuntimeError("모델 실패")

    monkeypatch.setattr(gemini_service.client.models, "generate_content", boom)

    result = gemini_service.chat_reply_with_actions([], "아무 말")

    assert result["reply"] == ""
    assert result["add_todos"] == []


def test_병합_호출이_빈_답변을_주면_빈_문자열이다(monkeypatch):
    """호출부가 빈 답변일 때 봇 메시지를 안 남기도록 판단할 수 있어야 한다."""
    import json

    class FakeResponse:
        text = json.dumps({"reply": "   ", "add_todos": []})

    monkeypatch.setattr(
        gemini_service.client.models, "generate_content", lambda **kw: FakeResponse()
    )

    result = gemini_service.chat_reply_with_actions([], "아무 말")
    assert result["reply"] == ""
    assert result["add_todos"] == []
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `./venv/bin/python -m pytest tests/test_chat_commands.py -k "병합_호출" -v`
Expected: FAIL — `AttributeError: module 'gemini_service' has no attribute 'chat_reply_with_actions'`

- [ ] **Step 3: 스키마·프롬프트·함수를 추가한다**

`gemini_service.py`의 `extract_chat_actions` 정의 바로 아래(`:594` 부근)에 추가한다.

```python
# 추출 스키마에 답변 한 필드를 더한 것이다. 별도로 선언하지 않고 파생시키는
# 이유: 추출 필드가 바뀌었을 때 한쪽만 고쳐 두 경로가 갈라지는 걸 막는다.
_CHAT_TURN_SCHEMA = {
    "type": "OBJECT",
    "required": ["reply", *_EXTRACTION_SCHEMA["required"]],
    "properties": {
        "reply": {"type": "STRING"},
        **_EXTRACTION_SCHEMA["properties"],
    },
}

_CHAT_TURN_PROMPT = """
너는 스타트업의 업무 흐름을 꿰뚫는 꼼꼼한 PM 비서 '@비서'다.
아래 [메시지]에 대해 두 가지를 **한 번에** 해라.

1. reply — 동료에게 할 답변. 2~4문장 이내로 짧고 친근하게, 한국어 존댓말로.
   [지난 대화]의 맥락을 반영한다.

2. 할 일(todo)과 일정(schedule) 변경사항 추출.
   - 명확한 업무 지시, 약속, 마감일 언급만 추출한다. 잡담·인사·질문만 있으면 무시한다.
   - 이미 존재할 법한 할 일/일정을 완료·취소했다는 언급이면 해당 hint 배열에
     핵심 키워드만 짧게 넣는다.
   - 날짜는 반드시 위에 주어진 오늘 날짜를 기준으로 YYYY-MM-DD 절대 날짜로 변환한다.
   - 추출할 내용이 없으면 모든 배열을 빈 배열로 둔다.

추출할 게 없다고 해서 reply를 비우지 마라. 두 가지는 서로 독립이다.
"""


def chat_reply_with_actions(recent_messages: list[dict], message: str) -> dict:
    """채팅 한 턴에서 답변과 액션 추출을 한 번의 호출로 받는다.

    나누면 같은 문장을 두 번 읽히게 되고, 하루 20건짜리 한도에서 메시지 하나가
    2건을 먹는다. answer_assistant가 이미 같은 구조(한 응답에 답변 + 액션)로
    돌고 있어 새 방식이 아니다.

    합친 대가로 실패 격리가 없다 — 한 번의 실패가 답변과 액션을 둘 다 잃는다.
    되돌리려면 호출부에서 extract_chat_actions + generate_bot_reply로 돌아가면
    된다. 두 함수는 /할일·/질문이 쓰고 있어 그대로 남아 있다.
    """
    prompt = (
        f"{korean_date_context()}\n\n{_CHAT_TURN_PROMPT}\n\n"
        f"[지난 대화]\n{_format_history(recent_messages) or '(없음)'}\n\n"
        f"[메시지]\n{message}"
    )

    empty = {**_EMPTY_EXTRACTION, "reply": ""}
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_CHAT_TURN_SCHEMA,
            ),
        )
        data = json.loads(response.text)
        return {**empty, **data, "reply": (data.get("reply") or "").strip()}
    except Exception as exc:
        _reraise_if_quota(exc, "chat.turn.quota_exceeded")
        logger.warning("채팅 턴 처리 실패", extra={"event": "chat.turn.failed"})
        return dict(empty)
```

`_format_history`는 `gemini_service.py:596`에 정의돼 이 함수보다 아래에 있다. 파이썬은 호출 시점에 이름을 찾으므로 정의 순서는 문제가 되지 않는다.

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `./venv/bin/python -m pytest tests/test_chat_commands.py -k "병합_호출" -v`
Expected: PASS (3 tests)

- [ ] **Step 5: 호출부를 바꾼다**

`main.py:1083-1089`의 `elif room.ai_mode:` 블록을 교체한다. 변경 전:

```python
    elif room.ai_mode:
        # AI가 방에 들어와 있을 때만 대화를 읽는다. 평소엔 Gemini를 호출하지 않는다.
        actions = gemini_service.extract_chat_actions(content)
        _apply_extracted_actions(db, group_id, actions)
        db.commit()
        reply_text = gemini_service.generate_bot_reply(_recent_history(db, room_id), content)
        bot_message = _post_bot_message(db, room_id, reply_text)
```

변경 후:

```python
    elif room.ai_mode:
        # AI가 방에 들어와 있을 때만 대화를 읽는다. 평소엔 Gemini를 호출하지 않는다.
        # 답변과 액션 추출을 한 번에 받는다 — 나눠 부르면 메시지 하나가
        # 하루 한도에서 2건을 먹는다.
        turn = gemini_service.chat_reply_with_actions(_recent_history(db, room_id), content)
        _apply_extracted_actions(db, group_id, turn)
        db.commit()
        # 실패하면 reply가 빈 문자열이다. 빈 말풍선을 남기지 않는다.
        if turn["reply"]:
            bot_message = _post_bot_message(db, room_id, turn["reply"])
```

- [ ] **Step 6: 전체 테스트를 돌린다**

Run: `./venv/bin/python -m pytest -q 2>&1 | tail -20`

`tests/test_chat_commands.py`의 기존 테스트들이 `extract_chat_actions`·`generate_bot_reply`를 monkeypatch 하고 있어(`:42-43`, `:125`, `:142` 등) 일반 메시지 경로 테스트가 깨진다. 그 테스트들만 `chat_reply_with_actions`를 patch 하도록 고친다 — patch 함수는 아래 형태를 돌려준다.

```python
def _fake_turn(reply="네, 확인했습니다.", **over):
    empty = {
        "add_todos": [],
        "complete_todo_hints": [],
        "delete_todo_hints": [],
        "add_schedules": [],
        "delete_schedule_hints": [],
    }
    return {**empty, **over, "reply": reply}
```

`/할일`·`/질문` 명령 테스트는 그대로 둔다 — 그 경로는 안 바뀐다.

Expected: 296 passed

- [ ] **Step 7: 병합 전후 품질을 눈으로 비교한다**

설계 문서에 "구현 중 확인한다"고 적어둔 항목이다. 백엔드를 띄우고 채팅방에서 `/help`로 AI를 부른 뒤, 아래 세 입력을 넣어 답변과 추출 결과를 기록한다.

```
1. "내일까지 견적서 보낼게요"
   → 할 일 1건 + 답변
2. "점심 뭐 드실래요"
   → 추출 0건 + 답변 (잡담을 안 뽑는지)
3. "지난주 시안 건은 끝냈고, 8월 30일에 출시 미팅 잡아주세요"
   → 완료 힌트 1 + 일정 1 + 답변
```

`git stash`로 되돌린 상태에서 같은 입력을 넣어 비교한다. 답변 길이·말투가 눈에 띄게 나빠졌거나 2번에서 잡담을 추출하면 **되돌린다** — `main.py` 호출부를 두 함수 방식으로 복귀시키고 이 태스크를 중단한 뒤 보고한다.

결과는 커밋 메시지 본문에 3줄로 남긴다(트러블슈팅이 아니라 설계 검증이므로 `TROUBLESHOOTING.md`가 아니다).

- [ ] **Step 8: 커밋한다**

```bash
git add gemini_service.py main.py tests/test_chat_commands.py
git commit -m "feat: 채팅 한 턴을 Gemini 호출 1건으로 처리

답변과 액션 추출을 한 응답에서 받는다. answer_assistant가 이미 쓰는
구조다. 메시지당 2건에서 1건으로 줄어 사용자 몫 12건이 메시지 12개가 된다.

품질 비교(입력 3종): <Step 7 결과 3줄>"
```

---

### Task 4: 게이트웨이 — `claim`을 필수 인자로

`gemini_service`의 모든 Gemini 호출 함수가 `claim: Callable[[], bool]`을 **필수 키워드 인자**로 받게 한다. 빠뜨리면 `TypeError`로 즉시 터지므로 예산을 우회할 수 없다. 스윕의 `_claim_sweep_call`은 이 시점에 걷어낸다.

**Files:**
- Create: `tests/test_call_budget_gateway.py`
- Modify: `gemini_service.py` (`_spend` 래퍼 + 9개 함수 시그니처)
- Modify: `main.py` (8개 호출부), `routers/assistant.py:53`, `routers/commitments.py:181-182`, `commitment_service.py`

**Interfaces:**
- Consumes: `call_budget.user_claimer()`, `call_budget.sweep_claimer()`, `gemini_service.QuotaExceeded`
- Produces: `gemini_service`의 9개 공개 호출 함수가 전부 `*, claim: Callable[[], bool]` 을 필수로 받는다.

- [ ] **Step 1: 강제를 검사하는 테스트를 쓴다**

`tests/test_call_budget_gateway.py`를 만든다. 이 파일이 이 태스크의 핵심이다.

```python
"""게이트웨이가 실제로 강제되는지 검사한다.

TS-035는 korean_date_context()를 호출부 여섯 곳 중 둘에 빠뜨린 사건이었다.
테스트 265개가 전부 초록인데 마감일이 799일 어긋나 있었다 — 빠뜨려도 조용히
돌아갔기 때문이다. 예산에서 같은 일이 벌어지면 조용히 한도를 넘는다.

그래서 "빠뜨릴 수 없음"을 사람의 주의가 아니라 테스트로 잡는다.
"""

import inspect

import pytest

import gemini_service

# Gemini를 실제로 부르는 공개 함수. 새 함수를 추가하면 여기에도 넣어야 한다.
GEMINI_CALLERS = [
    "extract_chat_commitments",
    "summarize_upload",
    "classify_document_category",
    "extract_chat_actions",
    "chat_reply_with_actions",
    "summarize_conversation",
    "draft_document_from_conversation",
    "generate_bot_reply",
    "answer_assistant",
]


@pytest.mark.parametrize("name", GEMINI_CALLERS)
def test_모든_호출_함수가_claim을_필수로_받는다(name):
    fn = getattr(gemini_service, name)
    params = inspect.signature(fn).parameters

    assert "claim" in params, f"{name}이 claim을 안 받는다 — 예산 밖에서 호출이 나간다"
    assert params["claim"].default is inspect.Parameter.empty, (
        f"{name}의 claim에 기본값이 있다. 빠뜨려도 조용히 돌아가면 강제가 아니다"
    )
    assert params["claim"].kind is inspect.Parameter.KEYWORD_ONLY, (
        f"{name}의 claim이 키워드 전용이 아니다 — 위치 인자로 밀려 들어갈 수 있다"
    )


def test_목록이_실제_호출_함수를_빠짐없이_담았는가():
    """generate_content를 부르는데 GEMINI_CALLERS에 없는 함수를 잡는다.
    목록 자체가 낡는 것을 막는 안전장치다."""
    listed = set(GEMINI_CALLERS)

    for name, fn in inspect.getmembers(gemini_service, inspect.isfunction):
        if name.startswith("_") or fn.__module__ != gemini_service.__name__:
            continue
        if "generate_content" in inspect.getsource(fn) and name not in listed:
            pytest.fail(f"{name}이 generate_content를 부르는데 GEMINI_CALLERS에 없다")


def test_claim이_False면_호출하지_않고_QuotaExceeded를_올린다(monkeypatch):
    def must_not_be_called(**kwargs):
        raise AssertionError("예산이 없는데 Gemini를 불렀다")

    monkeypatch.setattr(gemini_service.client.models, "generate_content", must_not_be_called)

    with pytest.raises(gemini_service.QuotaExceeded):
        gemini_service.generate_bot_reply([], "질문", claim=lambda: False)


def test_claim이_True면_정상_호출된다(monkeypatch):
    class FakeResponse:
        text = "네, 확인했습니다."

    monkeypatch.setattr(
        gemini_service.client.models, "generate_content", lambda **kw: FakeResponse()
    )

    result = gemini_service.generate_bot_reply([], "질문", claim=lambda: True)
    assert result == "네, 확인했습니다."


def test_claim은_호출당_한_번만_불린다(monkeypatch):
    """한 함수가 claim을 두 번 부르면 장부가 실제보다 빨리 준다."""

    class FakeResponse:
        text = "네."

    monkeypatch.setattr(
        gemini_service.client.models, "generate_content", lambda **kw: FakeResponse()
    )
    calls = []
    gemini_service.generate_bot_reply([], "질문", claim=lambda: calls.append(1) or True)
    assert len(calls) == 1


def test_QuotaExceeded는_함수_내부_except에_먹히지_않는다(monkeypatch):
    """_spend를 try 안에 두면 각 함수의 except Exception이 잡아
    None이나 빈 결과로 뭉갠다. 그러면 소진이 '모델 실패'로 보인다."""

    monkeypatch.setattr(
        gemini_service.client.models,
        "generate_content",
        lambda **kw: (_ for _ in ()).throw(AssertionError("불리면 안 된다")),
    )

    with pytest.raises(gemini_service.QuotaExceeded):
        gemini_service.extract_chat_actions("아무 말", claim=lambda: False)
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `./venv/bin/python -m pytest tests/test_call_budget_gateway.py -v`
Expected: FAIL — 9개 파라미터 테스트가 `AssertionError: …이 claim을 안 받는다`

- [ ] **Step 3: 게이트웨이 래퍼를 추가한다**

`gemini_service.py`의 `_reraise_if_quota` 정의 바로 아래(`:366` 부근)에 추가한다.

```python
def _spend(claim: Callable[[], bool], event: str) -> None:
    """호출 직전에 예산 1건을 선점한다. 없으면 QuotaExceeded.

    모든 Gemini 호출이 이 문을 지난다. 호출부마다 검사를 흩뿌리면 언젠가
    한 곳이 빠지고, 빠진 곳은 조용히 예산 밖에서 돈다.

    선차감이다. 이 뒤 호출이 실패해도 되돌리지 않는다 — 요청이 나갔으면
    실제 한도는 이미 깎였고, 되돌리면 실패 재시도가 남은 예산을 태운다.
    """
    if not claim():
        logger.warning("AI 일일 예산 소진", extra={"event": event})
        raise QuotaExceeded
```

파일 상단에 `from typing import Callable` 을 추가한다.

- [ ] **Step 4: 9개 함수 시그니처를 바꾼다**

각 함수의 파라미터 끝에 `*, claim: Callable[[], bool]` 을 넣고, 본문 첫머리에 `_spend(claim, "<event>")` 를 넣는다. `summarize_upload`는 `async def`지만 `_spend`는 동기이므로 `await` 없이 부른다.

| 함수 | 시그니처 끝 | `_spend` event |
|---|---|---|
| `extract_chat_commitments` | `(history_text: str, *, claim: Callable[[], bool])` | `"commitment.extract.no_budget"` |
| `summarize_upload` | `(file: UploadFile, prompt: str, *, claim: Callable[[], bool])` | `"document.summarize.no_budget"` |
| `classify_document_category` | `(summary_text: str, *, claim: Callable[[], bool])` | `"document.classify.no_budget"` |
| `extract_chat_actions` | `(message: str, *, claim: Callable[[], bool])` | `"chat.extract.no_budget"` |
| `chat_reply_with_actions` | `(recent_messages: list[dict], message: str, *, claim: Callable[[], bool])` | `"chat.turn.no_budget"` |
| `summarize_conversation` | `(messages: list[dict], *, claim: Callable[[], bool])` | `"chat.summary.no_budget"` |
| `draft_document_from_conversation` | `(messages: list[dict], title: str, *, claim: Callable[[], bool])` | `"chat.draft.no_budget"` |
| `generate_bot_reply` | `(recent_messages: list[dict], new_message: str, *, claim: Callable[[], bool])` | `"chat.reply.no_budget"` |
| `answer_assistant` | `(context_text: str, history: list[dict], message: str, *, claim: Callable[[], bool])` | `"assistant.answer.no_budget"` |

두 가지를 반드시 지킨다.

1. **`_spend`는 `try:` 바깥에 둔다.** 안에 두면 `QuotaExceeded`가 각 함수의 `except Exception:`에 잡혀 `None`이나 빈 결과로 뭉개진다. 그러면 소진이 "모델 실패"로 보인다. Step 1의 마지막 테스트가 이걸 잡는다.
2. **조기 반환은 `_spend`보다 앞에 둔다.** `draft_document_from_conversation`의 `if not messages: return None` 이 그 예다. 호출하지 않을 것에 예산을 태우면 안 된다.

- [ ] **Step 5: 게이트웨이 테스트가 통과하는지 확인한다**

Run: `./venv/bin/python -m pytest tests/test_call_budget_gateway.py -v`
Expected: PASS (14 tests)

- [ ] **Step 6: 호출부를 전부 갱신한다**

`TypeError`로 전부 터지므로 하나씩 고친다. `main.py`, `routers/assistant.py`, `commitment_service.py` 상단에 `import call_budget` 을 추가한다.

| 위치 | 넘길 값 |
|---|---|
| `main.py:197` (`summarize_upload`) | `claim=call_budget.user_claimer()` |
| `main.py:218` (`classify_document_category` 폴백) | `claim=call_budget.user_claimer()` |
| `main.py:1004` (`summarize_conversation`) | `claim=call_budget.user_claimer()` |
| `main.py:1009` (`draft_document_from_conversation`) | `claim=call_budget.user_claimer()` |
| `main.py:1021` 부근 (`classify_document_category` 폴백, Task 2) | `claim=call_budget.user_claimer()` |
| `main.py:1040` (`extract_chat_actions`, `/할일`) | `claim=call_budget.user_claimer()` |
| `main.py:1052` (`generate_bot_reply`, `/질문`) | `claim=call_budget.user_claimer()` |
| `main.py` 일반 메시지 (`chat_reply_with_actions`, Task 3) | `claim=call_budget.user_claimer()` |
| `routers/assistant.py:53` (`answer_assistant`) | `claim=call_budget.user_claimer()` |
| `commitment_service.py:310` 부근 (`extract_chat_commitments`) | `claim=call_budget.sweep_claimer()` |

- [ ] **Step 7: 스윕의 옛 예산 코드를 걷어낸다**

`commitment_service.py`에서 삭제한다.

- `SWEEP_DAILY_BUDGET` 상수 (`:198`)
- `sweep_calls_used_today` (`:201-206`)
- `_claim_sweep_call` (`:209-261`)
- `CallBudget` import (Task 1 Step 6에서 바꿔둔 것)

`:302`의 `if not _claim_sweep_call(db):` 블록을 지우고, 예산 소진 판정을 `extract_chat_commitments`가 올리는 `QuotaExceeded`로 옮긴다.

`_scan_room`은 `ScanResult`(NamedTuple, `commitment_service.py:269`)를 돌려준다. 예산 소진도 같은 형태로 돌려줘야 한다.

```python
    try:
        items = gemini_service.extract_chat_commitments(
            history, claim=call_budget.sweep_claimer()
        )
    except gemini_service.QuotaExceeded:
        return ScanResult(SCAN_NO_BUDGET)
```

기존 `items = gemini_service.extract_chat_commitments(history)` (`:310`) 한 줄이 위 블록으로 바뀌는 것이다. 그 아래의 `if items is None: raise RuntimeError(...)` 는 그대로 둔다 — 호출 실패와 예산 소진은 다른 상태이고, 실패만 포인터를 전진시키지 않아야 한다.

`:383` 부근 로그의 `"budget": SWEEP_DAILY_BUDGET` 를 `"budget": call_budget.DAILY_TOTAL - call_budget.RESERVE` 로 바꾼다.

`routers/commitments.py:181-182`의 `budget_used`/`budget_total` 두 줄을 지운다 — Task 5에서 `ai_budget`으로 옮긴다.

- [ ] **Step 8: 전체 테스트를 돌린다**

Run: `./venv/bin/python -m pytest -q 2>&1 | tail -30`

고쳐야 할 것들:
- `tests/test_commitment_sweep.py`가 `SWEEP_DAILY_BUDGET`·`sweep_calls_used_today`를 참조하면 `call_budget` 쪽으로 옮긴다.
- `tests/test_summary_routes.py`·`tests/test_assistant_gemini.py`가 `gemini_service` 함수를 직접 부르는 곳에 `claim=lambda: True` 를 추가한다.

Expected: 전부 초록 (약 310건)

- [ ] **Step 9: 커밋한다**

```bash
git add gemini_service.py main.py routers/ commitment_service.py tests/
git commit -m "feat: 모든 Gemini 호출이 예산 문을 지나게 한다

claim을 필수 키워드 인자로 만들어 빠뜨리면 TypeError로 터지게 했다.
시그니처를 순회해 강제를 검사하는 테스트를 함께 둔다 — TS-035처럼
'빠뜨려도 조용히 도는' 상태를 만들지 않기 위해서다.

스윕 전용 예산(_claim_sweep_call)은 전역 장부로 흡수했다."
```

---

### Task 5: 응답 형식과 429 통일

`meta.ai_budget`을 신설하고, 소진 응답 코드를 `AI_DAILY_BUDGET_EXHAUSTED`로 통일한다.

**Files:**
- Modify: `routers/commitments.py` (`_ai_budget_meta` 신설, meta 조립)
- Modify: `main.py:202-208`, `main.py` 채팅 경로, `routers/assistant.py:60-66`
- Test: `tests/test_commitment_routes.py`, `tests/test_assistant_routes.py`

**Interfaces:**
- Consumes: `call_budget.used_today`, `call_budget.DAILY_TOTAL`, `call_budget.resets_at`, `routers/commitments._utc_iso`
- Produces: `GET /api/v1/commitments` 의 `meta`가
  `{"total": …, "limit": …, "hasNext": …, "sweep": {"last_at","scanned","found"}, "ai_budget": {"used","total","resets_at"}}`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_commitment_routes.py`에 추가한다. 이 파일의 `_setup(client)`(`:6`)은 `(headers, group_a_id, group_b_id)` 3튜플을 돌려준다.

```python
def test_약속_목록_meta에_ai_budget이_실린다(client):
    auth, group_id, _ = _setup(client)

    res = client.get("/api/v1/commitments", params={"group_id": group_id}, headers=auth)
    assert res.status_code == 200

    budget = res.json()["meta"]["ai_budget"]
    assert budget["total"] == 20
    assert budget["used"] >= 0
    assert budget["resets_at"].endswith("Z")


def test_sweep_meta에는_예산이_없다(client):
    """예산은 스윕 소속이 아니다. 두 곳에 두면 어느 쪽이 참인지 모른다."""
    auth, group_id, _ = _setup(client)

    res = client.get("/api/v1/commitments", params={"group_id": group_id}, headers=auth)
    assert set(res.json()["meta"]["sweep"]) == {"last_at", "scanned", "found"}
```

`tests/test_assistant_routes.py`에 추가한다. 이 파일에는 `_setup(client)`(`:22`)과 `_ask(client, token, group_id, ...)`(`:30`)가 있다. 두 헬퍼의 반환·인자 형태를 파일 상단에서 확인하고 아래를 그에 맞춘다.

```python
def test_예산_소진이면_429와_통일된_코드를_준다(client, monkeypatch):
    import call_budget

    monkeypatch.setattr(call_budget, "DAILY_TOTAL", 0)
    monkeypatch.setattr(call_budget, "RESERVE", 0)

    token, group_id = _setup(client)
    res = _ask(client, token, group_id, message="오늘 뭐 해야 해?")

    assert res.status_code == 429
    assert res.json()["error"]["code"] == "AI_DAILY_BUDGET_EXHAUSTED"
```

**주의**: 이 테스트는 `answer_assistant`를 monkeypatch 하지 않는다. 예산이 0이라 `_spend`가 Gemini 호출 전에 `QuotaExceeded`를 올리므로 실제 API를 부르지 않는다 — 그게 이 테스트가 확인하려는 것이다.

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `./venv/bin/python -m pytest tests/test_commitment_routes.py -k "ai_budget or sweep_meta" tests/test_assistant_routes.py -k "예산_소진" -v`
Expected: FAIL — `KeyError: 'ai_budget'`, 코드 불일치

- [ ] **Step 3: `_ai_budget_meta`를 추가한다**

`routers/commitments.py`의 `_sweep_meta` 아래에 넣고, 상단에 `import call_budget` 을 추가한다.

```python
def _ai_budget_meta(db: Session) -> dict:
    """오늘 AI 호출을 얼마나 썼는지. 화면이 소진 전에 미리 막기 위한 값이다.

    스윕 메타와 분리해 둔다 — 예산은 스윕만의 것이 아니라 요약·비서·채팅이
    함께 쓴다. sweep 아래에 두면 스윕이 안 도는 날엔 예산도 없는 줄 안다.

    이 조회에 얹는 이유: 프론트가 30초마다 이 엔드포인트를 부르고 있어
    별도 폴링을 만들 필요가 없다.
    """
    return {
        "used": call_budget.used_today(db),
        "total": call_budget.DAILY_TOTAL,
        "resets_at": _utc_iso(call_budget.resets_at()),
    }
```

`:248` 부근의 meta 조립에 `"ai_budget": _ai_budget_meta(db),` 를 넣는다.

- [ ] **Step 4: 429 코드를 통일한다**

세 곳의 `detail`을 아래로 맞춘다.

```python
            detail={
                "code": "AI_DAILY_BUDGET_EXHAUSTED",
                "message": "오늘 AI 한도를 다 썼습니다. 내일 다시 이용해주세요.",
            },
```

- `main.py:202-208` — `DOCUMENT_QUOTA_EXCEEDED` 를 교체
- `routers/assistant.py:60-66` — `ASSISTANT_QUOTA_EXCEEDED` 를 교체
- 채팅 메시지 POST 경로 — `chat_reply_with_actions`가 올리는 `QuotaExceeded`를 잡는 곳이 아직 없다. `elif room.ai_mode:` 블록을 `try:`로 감싸고 같은 429를 올린다.

```python
    elif room.ai_mode:
        try:
            turn = gemini_service.chat_reply_with_actions(
                _recent_history(db, room_id), content, claim=call_budget.user_claimer()
            )
        except gemini_service.QuotaExceeded:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "AI_DAILY_BUDGET_EXHAUSTED",
                    "message": "오늘 AI 한도를 다 썼습니다. 내일 다시 이용해주세요.",
                },
            )
        _apply_extracted_actions(db, group_id, turn)
        db.commit()
        if turn["reply"]:
            bot_message = _post_bot_message(db, room_id, turn["reply"])
```

- [ ] **Step 5: 전체 테스트를 돌린다**

Run: `./venv/bin/python -m pytest -q 2>&1 | tail -20`
Expected: 전부 초록

- [ ] **Step 6: 커밋한다**

```bash
git add routers/ main.py tests/
git commit -m "feat: meta.ai_budget 신설과 소진 응답 코드 통일

예산을 sweep 메타에서 꺼내 별도 필드로 둔다. 소진은 전 경로가
429 + AI_DAILY_BUDGET_EXHAUSTED로 답한다."
```

---

### Task 6: 프론트 — `AiBudget` 타입과 대시보드 표시

**Files:**
- Modify: `onque-frontend/lib/api.ts`, `onque-frontend/lib/sweep-status.ts`, `onque-frontend/lib/sweep-status.test.ts`
- Modify: `onque-frontend/components/WorkspaceContext.tsx`, `onque-frontend/components/dashboard/SummaryColumn.tsx`
- Modify: `onque-frontend/package.json` (테스트 타임존 고정)

**Interfaces:**
- Consumes: `meta.ai_budget` (Task 5)
- Produces:
  - `AiBudget = { used: number; total: number; resets_at: string }`
  - `SweepMeta = { last_at: string | null; scanned: number | null; found: number | null }`
  - `CommitmentListMeta = ListMeta & { sweep: SweepMeta; ai_budget: AiBudget }`
  - `useWorkspace()`가 `aiBudget: AiBudget | null` 을 추가로 돌려준다
  - `formatResetTime(iso: string): string | null` — `lib/sweep-status.ts`
  - `buildSweepStatus(sweep, now)`의 반환에서 `exhausted`가 사라지고 `{ line }` 만 남는다

- [ ] **Step 1: 테스트를 고치고 새 테스트를 쓴다**

`lib/sweep-status.test.ts`에서:
- `meta()` 헬퍼의 `budget_used`, `budget_total` 두 줄을 지운다
- `'예산을 다 쓰면 소진으로 표시한다'`, `'한 번도 안 훑은 상태에서도 예산 소진은 따로 판정한다'` 두 테스트를 삭제한다
- `'메타가 없으면 보여줄 줄이 없다'`의 기대값을 `{ line: null }` 로 바꾼다

파일 상단 import에 `formatResetTime`을 추가하고 아래를 덧붙인다.

```typescript
describe('formatResetTime', () => {
  it('ISO 문자열을 사람이 읽는 시각으로 바꾼다', () => {
    // 2026-08-18T00:00:00Z = KST 오전 9시
    expect(formatResetTime('2026-08-18T00:00:00Z')).toBe('8월 18일 오전 9시');
  });

  it('파싱할 수 없으면 null이다 — 엉뚱한 시각을 지어내지 않는다', () => {
    expect(formatResetTime('언젠가')).toBeNull();
  });
});
```

이 테스트는 실행 환경 타임존에 의존한다. `package.json`의 `"test"` 를 `"TZ=Asia/Seoul vitest run"` 으로 바꿔 고정한다.

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `cd onque-frontend && npx vitest run lib/sweep-status.test.ts`
Expected: FAIL — `formatResetTime is not a function`

- [ ] **Step 3: 타입과 함수를 고친다**

`lib/api.ts`:

```typescript
/** 백그라운드 스윕이 직전에 무엇을 했는지.
 *
 * 아직 한 번도 대화를 훑지 않았으면 세 값이 모두 null이다. 0이 아닌 이유는
 * "훑었는데 못 찾음"과 "아직 훑은 적 없음"이 다른 상태이기 때문이다. */
export type SweepMeta = {
  last_at: string | null;
  scanned: number | null;
  found: number | null;
};

/** 오늘 AI 호출을 얼마나 썼는지.
 *
 * 스윕 메타와 분리돼 있다 — 이 예산은 스윕만의 것이 아니라 요약·비서·채팅이
 * 함께 쓴다. 남은 게 없으면 화면이 입력을 미리 막는 데 쓴다. */
export type AiBudget = {
  used: number;
  total: number;
  resets_at: string;
};

export type CommitmentListMeta = ListMeta & { sweep: SweepMeta; ai_budget: AiBudget };
```

`lib/sweep-status.ts`: `SweepStatus`에서 `exhausted`를 빼고 `{ line: string | null }` 만 남긴다. `buildSweepStatus`의 각 `return`에서 `exhausted`를 제거하고, 파일 끝에 추가한다.

```typescript
/** "8월 18일 오전 9시". 소진 안내에서 언제 풀리는지 말하는 데 쓴다.
 *
 * 서버가 UTC로 주고 표시 시점 변환은 클라이언트 책임이다(api-contract 규약).
 * 파싱 실패는 null이다 — 안내에서 시각을 빼는 게 틀린 시각을 말하는 것보다 낫다. */
export function formatResetTime(iso: string): string | null {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return null;
  return at.toLocaleString('ko-KR', { month: 'long', day: 'numeric', hour: 'numeric' });
}
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `cd onque-frontend && npm test`
Expected: PASS

- [ ] **Step 5: WorkspaceContext와 대시보드를 고친다**

`WorkspaceContext.tsx`:
- `import { … type AiBudget } from '@/lib/api'`
- `const [aiBudget, setAiBudget] = useState<AiBudget | null>(null);`
- 그룹이 없을 때 `setAiBudget(null);` (기존 `setSweep(null)` 옆)
- 로드 성공 시 `setAiBudget(proposed.meta?.ai_budget ?? null);`
- 컨텍스트 타입과 `value` 객체에 `aiBudget` 추가. 주석은 아래로 둔다.

```typescript
  /** 오늘 AI 호출 잔량. 응답에 없으면 null.
   *
   * 30초마다 도는 이 조회에 얹혀 온다. 입력구를 미리 막는 데 쓰므로
   * 화면 여러 곳이 같은 값을 봐야 한다. */
  aiBudget: AiBudget | null;
```

`SummaryColumn.tsx`의 `SweepStatusLine`을 교체한다.

```tsx
function SweepStatusLine() {
  const { sweep, aiBudget, lastSyncedAt } = useWorkspace();
  if (sweep === null || lastSyncedAt === null) return null;

  const status = buildSweepStatus(sweep, lastSyncedAt);
  if (status.line === null && aiBudget === null) return null;

  const exhausted = aiBudget !== null && aiBudget.used >= aiBudget.total;

  return (
    <div className="mt-4 border-t border-hairline pt-4">
      <p className="text-[10px] font-semibold text-fg-dim">자동 확인</p>
      {status.line && (
        <p className="mt-2 text-[11px] leading-relaxed text-fg-muted">{status.line}</p>
      )}
      {aiBudget && (
        <p className="mt-1 text-[10px] tabular-nums text-fg-dim">
          오늘 {aiBudget.used}/{aiBudget.total}
          {exhausted && ' · 한도를 다 써 내일 이어서 확인합니다'}
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 6: 테스트·빌드를 돌린다**

Run: `cd onque-frontend && npm test && npx next build 2>&1 | tail -15`
Expected: 테스트 통과, 빌드 성공

- [ ] **Step 7: 커밋한다**

```bash
git add onque-frontend/lib onque-frontend/components onque-frontend/package.json
git commit -m "feat: 예산을 스윕 메타에서 분리해 AiBudget으로 다룬다

대시보드가 '오늘 7/20'을 전역 예산 기준으로 보여준다."
```

---

### Task 7: 프론트 — 소진 시 사전 차단

잔량 0이면 세 입력구를 막고 그 자리에 사유를 쓴다. 화면 차단은 헛수고를 없애는 것이지 보안이 아니다 — 서버는 Task 5에서 이미 막고 있다.

**Files:**
- Create: `onque-frontend/components/ui/BudgetNotice.tsx`
- Modify: `onque-frontend/components/ChatWindow.tsx`, `onque-frontend/components/UploadPanel.tsx`, `onque-frontend/components/AssistantPanel.tsx`

**Interfaces:**
- Consumes: `useWorkspace().aiBudget` (Task 6), `formatResetTime`
- Produces: `<BudgetNotice />` — 잔량이 있으면 `null`을 렌더한다. 호출부는 조건 없이 놓기만 하면 된다.

- [ ] **Step 1: 컴포넌트를 만든다**

`onque-frontend/components/ui/BudgetNotice.tsx`:

```tsx
'use client';

import { useWorkspace } from '@/components/WorkspaceContext';
import { formatResetTime } from '@/lib/sweep-status';

/** 오늘 AI 한도를 다 썼을 때 입력구 자리에 놓는 안내.
 *
 * 잔량이 있으면 아무것도 그리지 않아, 호출부는 조건 없이 놓기만 하면 된다.
 * 조건을 호출부마다 쓰면 세 곳 중 한 곳이 빠진다.
 *
 * 눌러보고 실패하게 두지 않는 이유: 하루 한도는 잠시 후에 안 풀린다.
 * "잠시 후 다시"를 믿고 재시도를 반복하면 앱이 고장난 것처럼 보인다. */
export function BudgetNotice() {
  const { aiBudget } = useWorkspace();
  if (aiBudget === null || aiBudget.used < aiBudget.total) return null;

  const resetsAt = formatResetTime(aiBudget.resets_at);

  return (
    <p
      role="status"
      className="rounded-xl border border-hairline bg-surface-2 px-4 py-3 text-xs leading-relaxed text-fg-muted"
    >
      오늘 AI 한도를 다 썼습니다.
      {resetsAt ? ` ${resetsAt}에 초기화됩니다.` : ' 내일 다시 이용해주세요.'}
    </p>
  );
}
```

- [ ] **Step 2: 세 곳에 적용한다**

각 컴포넌트에서 소진 여부를 계산해 입력·버튼에 `disabled`를 걸고, 폼 위에 `<BudgetNotice />`를 놓는다.

```tsx
const { aiBudget } = useWorkspace();
const budgetExhausted = aiBudget !== null && aiBudget.used >= aiBudget.total;
```

- **`ChatWindow.tsx`** — 입력 `<input>`과 전송 `<button>`에 `disabled={budgetExhausted || …}`.
  **AI가 방에 없으면(`ai_mode` 꺼짐) 막지 않는다** — 그 경로는 Gemini를 안 부른다.
  방의 `ai_mode`를 props로 받고 있는지 확인하고, 없으면 부모(`app/chat/page.tsx`)에서 전달한다.
  차단 조건은 `budgetExhausted && room.ai_mode` 다.
- **`UploadPanel.tsx`** — 업로드 버튼에 `disabled`, 패널 안에 `<BudgetNotice />`.
- **`AssistantPanel.tsx`** — 질문 입력과 전송 버튼에 `disabled`, 폼 위에 `<BudgetNotice />`.

- [ ] **Step 3: 테스트·lint·빌드를 돌린다**

Run: `cd onque-frontend && npm test && npx eslint . 2>&1 | tail -10 && npx next build 2>&1 | tail -12`
Expected: 테스트 통과 / **eslint 에러 5건 — 기준선과 같아야 한다. 늘면 그 자리에서 고친다** / 빌드 성공

- [ ] **Step 4: 브라우저로 확인한다**

백엔드를 예산 0으로 띄운다.

```bash
AI_DAILY_TOTAL=0 AI_BUDGET_RESERVE=0 ./venv/bin/python -m uvicorn main:app --reload
```

확인할 것:
- 대시보드에 "오늘 0/0" 과 소진 문구
- 채팅방(AI 있음)·업로드·비서 세 입력구가 전부 비활성 + 안내 노출
- 채팅방(AI 없음)은 **정상 동작** — Gemini를 안 부르므로 막으면 안 된다
- 안내 시각이 KST 기준 다음 날 오전 9시로 보이는지

- [ ] **Step 5: 커밋한다**

```bash
git add onque-frontend/components onque-frontend/app
git commit -m "feat: 한도 소진 시 입력을 미리 막고 언제 풀리는지 알린다

눌러보고 429를 받는 대신, 잔량 0이면 세 입력구를 비활성화하고
초기화 시각을 그 자리에 쓴다. AI가 없는 채팅방은 막지 않는다."
```

---

## 마무리 검증

- [ ] `./venv/bin/python -m pytest -q` — 전부 초록
- [ ] `cd onque-frontend && npm test` — 전부 초록
- [ ] `cd onque-frontend && npx eslint .` — 에러 5건 (기준선 유지, 늘면 안 됨)
- [ ] `cd onque-frontend && npx next build` — 성공
- [ ] `./venv/bin/python scripts/migrate_rename_sweep_budget.py` — 운영 DB에 적용
- [ ] `.env.example`에 `AI_DAILY_TOTAL=20`, `AI_BUDGET_RESERVE=12` 추가
- [ ] `TROUBLESHOOTING.md`의 TS-033(하루 20건 한도) 상태를 갱신 — "안내·낭비 해결(한도 자체는 미해결)"에 예산 구조와 소비 절감으로 무엇이 바뀌었는지 덧붙인다. 새 번호를 따지 않고 기존 항목에 잇는다(같은 원인이다)
- [ ] **실제 리셋 시각 실측** — 다음에 한도가 소진되는 날 언제 풀리는지 기록하고, UTC 자정 가정이 맞는지 확인한다. 어긋나면 `call_budget.resets_at()`을 고치고 TROUBLESHOOTING에 남긴다
