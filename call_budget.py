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
