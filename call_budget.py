"""Gemini 호출의 하루 예산 장부.

무료 티어는 하루 20건이고, 그 한도를 백그라운드 스윕과 사용자가 직접 부르는
요약·비서·채팅이 함께 쓴다. 장부가 없으면 오전 채팅이 한도를 다 먹고, 오후에
회의 녹음을 올린 사람이 소진을 만난다 — 시킨 일이 안 시킨 일 때문에 실패한다.

배분은 예비선 방식이다. 총량 하나만 세고 소비자별로 상한을 다르게 둔다.
사용자는 잔량이 있으면 끝까지 쓰고, 스윕은 예비선 위에서만 돈다.
장부를 둘로 나누지 않은 이유: 스윕이 3건만 쓴 날에도 사용자가 12에서
막히기 때문이다.
"""

import logging
import os
from datetime import date, datetime, time, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import db as db_module
from models import CallBudget

logger = logging.getLogger(__name__)

DAILY_TOTAL = int(os.getenv("AI_DAILY_TOTAL", "20"))
# 사용자 몫으로 떼어두는 양. 스윕은 이 선 위에서만 돈다.
RESERVE = int(os.getenv("AI_BUDGET_RESERVE", "12"))

# 명세 §2의 RESET_AT을 시간대로 구현한 것 — 리셋 '시각'은 이 시간대의 자정이다.
# 기본값이 태평양인 이유: Gemini 공식 문서가 "RPD quotas reset at midnight
# Pacific time"이라고 못박는다. UTC 자정으로 세면 KST 09:00에 장부만 0으로
# 돌아가고 실제 할당량은 KST 17시경까지 어제 것이라, 그 8시간 동안 화면은
# 쓸 수 있다고 하고 Gemini는 429를 준다.
#
# 고정 오프셋이 아니라 시간대인 이유: 서머타임에 UTC 오프셋이 한 시간 움직인다.
RESET_TZ = ZoneInfo(os.getenv("AI_BUDGET_RESET_TZ", "America/Los_Angeles"))

_CONSUMERS = ("user", "sweep")


def ceiling(consumer: str) -> int:
    """이 소비자가 넘을 수 없는 누적 호출 수.

    공개해 두는 이유: 호출부가 DAILY_TOTAL - RESERVE를 직접 계산하면 배분
    규칙을 바꿀 때 그 복제본만 조용히 어긋난다. 로그와 화면이 실제와 다른
    숫자를 말하는데 아무것도 안 터진다.
    """
    if consumer not in _CONSUMERS:
        # 조용히 통과시키면 예산 밖에서 호출이 나간다.
        raise ValueError(f"알 수 없는 소비자: {consumer}")
    return DAILY_TOTAL if consumer == "user" else DAILY_TOTAL - RESERVE


def _now() -> datetime:
    """리셋 기준 시간대의 현재 시각. 테스트가 시계를 고정할 수 있게 한 곳으로 모은다."""
    return datetime.now(RESET_TZ)


def _today() -> date:
    return _now().date()


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
    """장부가 초기화되는 시각 = RESET_TZ의 다음 자정.

    Gemini의 RPD 리셋과 같은 기준으로 센다. 화면이 이 값으로 "언제 풀리는지"를
    안내하므로, 장부와 실제 할당량의 기준이 어긋나면 안내가 틀린 시각을 말한다.
    """
    return datetime.combine(_today() + timedelta(days=1), time.min, tzinfo=RESET_TZ)


def _granted(db: Session, consumer: str) -> bool:
    """선점 성공을 남기고 True를 돌려준다.

    장부는 총량 하나만 세므로 소비자별 내역은 이 로그가 유일한 출처다. 20건이
    소진됐을 때 스윕이 먹었는지 채팅이 먹었는지 답할 수 없으면, 배분 규칙을
    조정할 근거가 없다.

    소비자와 사용량을 message에도 넣는 이유: 이 저장소는 로깅 포매터를 따로
    설정하지 않아 uvicorn 기본 핸들러가 message만 출력한다(_timed와 같은 사정).
    extra는 나중에 구조화 로깅을 붙일 때를 위해 같이 둔다.
    """
    used = used_today(db)
    logger.info(
        "AI 예산 선점 consumer=%s used=%d/%d", consumer, used, DAILY_TOTAL,
        extra={
            "event": "ai_budget.claim.granted",
            "consumer": consumer,
            "used": used,
            "total": DAILY_TOTAL,
        },
    )
    return True


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
    limit = ceiling(consumer)
    if limit < 1:
        return False

    today = _today()
    bumped = db.execute(
        update(CallBudget)
        .where(CallBudget.day == today, CallBudget.calls < limit)
        .values(calls=CallBudget.calls + 1)
        .execution_options(synchronize_session=False)
    )
    if bumped.rowcount == 1:
        db.commit()
        return _granted(db, consumer)

    # 행이 있는데 못 올렸다면 상한 도달이다. 삽입을 시도하면 안 된다.
    if db.execute(
        select(CallBudget.day).where(CallBudget.day == today)
    ).scalar_one_or_none() is not None:
        return False

    try:
        with db.begin_nested():
            db.execute(insert(CallBudget).values(day=today, calls=1))
        db.commit()
        return _granted(db, consumer)
    except IntegrityError:
        # 다른 요청이 먼저 오늘 행을 만들었다. 그 행 위에서 다시 겨룬다.
        retried = db.execute(
            update(CallBudget)
            .where(CallBudget.day == today, CallBudget.calls < limit)
            .values(calls=CallBudget.calls + 1)
            .execution_options(synchronize_session=False)
        )
        if retried.rowcount == 1:
            db.commit()
            return _granted(db, consumer)
        return False


def mark_exhausted() -> None:
    """실제 429를 받았을 때 장부를 오늘 상한까지 끌어올린다.

    장부가 실제 소비보다 낮으면 선제 차단이 무력해진다. 남았다고 보고 매 요청이
    Gemini를 두드려 429를 받아오므로, 호출을 아끼려고 만든 장부가 정작 아껴야
    하는 상태에서 아무것도 아끼지 않는다.

    장부는 우리 호출만 세지만 실제 할당량은 프로젝트 단위다 — 다른 경로(개발
    스크립트, 다른 배포본)가 같은 키를 쓰면 두 숫자는 어긋난다. 그 어긋남을
    바로잡을 수 있는 유일한 순간이 Gemini가 소진을 알려주는 이 시점이다.

    자기 세션을 여는 이유는 _claimer와 같다 — 요청 트랜잭션의 성패를 따라가면
    안 된다. 이미 소진된 사실은 요청이 실패해도 남아야 한다.
    """
    session = Session(bind=db_module.engine)
    try:
        today = _today()
        bumped = session.execute(
            update(CallBudget)
            .where(CallBudget.day == today, CallBudget.calls < DAILY_TOTAL)
            .values(calls=DAILY_TOTAL)
            .execution_options(synchronize_session=False)
        )
        if bumped.rowcount == 0 and session.execute(
            select(CallBudget.day).where(CallBudget.day == today)
        ).scalar_one_or_none() is None:
            # 하루의 첫 호출이 곧바로 429일 수 있다. 적을 행이 없다고 넘어가면
            # 보정이 통째로 빠진다.
            session.execute(insert(CallBudget).values(day=today, calls=DAILY_TOTAL))
        session.commit()
        logger.warning(
            "실제 한도 소진을 장부에 반영 total=%d", DAILY_TOTAL,
            extra={"event": "ai_budget.exhausted.synced", "total": DAILY_TOTAL},
        )
    finally:
        session.close()


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
