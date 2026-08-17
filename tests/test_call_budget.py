import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import call_budget
from models import CallBudget


def _set_used(db_session, calls, day=None):
    """오늘 장부를 특정 값으로 만들어 둔다.

    '오늘'은 UTC가 아니라 리셋 기준 시간대의 오늘이다. 하루 중 8시간가량은
    두 날짜가 다르므로, UTC로 잡으면 그 시간대에만 깨지는 테스트가 된다.
    """
    db_session.merge(CallBudget(day=day or call_budget._today(), calls=calls))
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
    yesterday = call_budget._today() - timedelta(days=1)
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


def _freeze(monkeypatch, moment_utc):
    """리셋 기준 시간대의 시계를 특정 순간에 고정한다.

    실행 시각에 따라 결과가 갈리는 테스트를 쓰지 않으려는 것이다 — 날짜 경계
    버그는 하루 중 8시간에만 나타나므로, 실시계로 재면 대부분의 시간대에
    조용히 초록이 된다.
    """
    monkeypatch.setattr(
        call_budget, "_now", lambda: moment_utc.astimezone(call_budget.RESET_TZ)
    )


def test_날짜_경계는_UTC가_아니라_리셋_기준_시간대다(client, monkeypatch):
    """Gemini 공식 문서: RPD는 태평양 자정에 리셋된다. UTC 자정(KST 09:00)으로
    세면 실제 할당량이 아직 어제 것인 8시간 동안 장부만 0으로 돌아간다 —
    화면은 '쓸 수 있다'고 하고 Gemini는 429를 준다. 장부 칸과 실호출을 둘 다
    태우는 자리다."""
    # UTC로는 이미 8월 18일이지만 태평양으로는 아직 8월 17일 22시인 순간
    _freeze(monkeypatch, datetime(2026, 8, 18, 5, 0, tzinfo=timezone.utc))

    assert call_budget._today() == date(2026, 8, 17)


def test_기준_시간대의_자정을_넘기면_날짜가_바뀐다(client, monkeypatch):
    _freeze(monkeypatch, datetime(2026, 8, 18, 6, 59, tzinfo=timezone.utc))
    assert call_budget._today() == date(2026, 8, 17)

    _freeze(monkeypatch, datetime(2026, 8, 18, 7, 0, tzinfo=timezone.utc))
    assert call_budget._today() == date(2026, 8, 18)


@pytest.mark.parametrize(
    "moment_utc, expected_utc",
    [
        # 서머타임(PDT, UTC-7). 태평양 8/18 00:00 = 8/18 07:00Z
        (
            datetime(2026, 8, 17, 20, 0, tzinfo=timezone.utc),
            datetime(2026, 8, 18, 7, 0, tzinfo=timezone.utc),
        ),
        # 표준시(PST, UTC-8). 태평양 1/16 00:00 = 1/16 08:00Z
        (
            datetime(2026, 1, 15, 20, 0, tzinfo=timezone.utc),
            datetime(2026, 1, 16, 8, 0, tzinfo=timezone.utc),
        ),
    ],
    ids=["서머타임", "표준시"],
)
def test_resets_at은_기준_시간대의_다음_자정이다(client, monkeypatch, moment_utc, expected_utc):
    """서머타임 때문에 UTC 오프셋이 계절마다 한 시간 움직인다. 고정 오프셋으로
    박아두면 1년의 절반이 한 시간 어긋난 시각을 안내한다."""
    _freeze(monkeypatch, moment_utc)

    resets = call_budget.resets_at()

    assert resets.tzinfo is not None
    assert resets.astimezone(timezone.utc) == expected_utc
    # 기준 시간대의 벽시계로는 언제나 자정이다.
    assert (resets.hour, resets.minute, resets.second) == (0, 0, 0)


def test_claimer는_호출부_세션_없이도_차감한다(client, db_session, monkeypatch):
    """`_claimer`는 세션을 넘겨받지 않는다 — 부르면 자기 세션을 열어 차감하고
    닫는다. 게이트웨이(`gemini_service`)가 DB를 모른 채 부를 수 있어야 하기
    때문이다. 여기서 재는 건 그 한 가지, 인자 없이 불러도 차감이 남는다는 것뿐이다.

    **여기서 재지 '못하는' 것**: "바깥 트랜잭션이 롤백해도 차감은 남는다"는
    `claim`의 핵심 보장이다. 이 하네스는 `tests/conftest.py`가 StaticPool +
    `sqlite:///:memory:`를 쓰므로 모든 Session이 같은 커넥션 하나를 공유한다 —
    별도 세션이 별도 트랜잭션이 아니라서 롤백 격리를 원리상 검증할 수 없다.
    실제 검증은 커넥션이 실제로 갈리는 운영 Postgres(Neon)에서만 가능하다.
    """
    monkeypatch.setattr(call_budget, "DAILY_TOTAL", 20)
    monkeypatch.setattr(call_budget, "RESERVE", 12)

    claimer = call_budget.user_claimer()
    assert claimer() is True

    fresh = call_budget.used_today(db_session)
    assert fresh == 1


def test_동시_선점은_상한을_넘지_않는다(tmp_path, monkeypatch):
    """명세 테스트 표의 "동시 선점에서 총량 초과 없음".

    conftest의 하네스로는 이걸 못 쓴다 — StaticPool + `sqlite:///:memory:`라
    모든 Session이 커넥션 하나를 공유해서 '동시'가 성립하지 않는다. 이 테스트만
    파일 SQLite에 자기 엔진을 따로 만들어 커넥션을 실제로 가른다.

    무엇을 잡는가: `claim`이 조건부 UPDATE에서 SELECT 후 UPDATE로 바뀌면 여러
    스레드가 같은 잔량을 읽고 전부 통과해 상한을 넘는다. 나가는 호출 하나마다
    장부 하나라는 불변조건이 깨지는 자리다.
    """
    monkeypatch.setattr(call_budget, "DAILY_TOTAL", 20)
    monkeypatch.setattr(call_budget, "RESERVE", 15)  # 스윕 상한 = 20 - 15 = 5

    engine = create_engine(
        f"sqlite:///{tmp_path / 'budget.db'}", connect_args={"timeout": 30}
    )
    CallBudget.__table__.create(engine)

    def one_claim(_):
        session = Session(bind=engine)
        try:
            return call_budget.claim(session, "sweep")
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(one_claim, range(12)))

    assert sum(results) == 5
    session = Session(bind=engine)
    try:
        assert call_budget.used_today(session) == 5
    finally:
        session.close()


def test_선점에_성공하면_소비자와_사용량을_남긴다(client, db_session, monkeypatch, caplog):
    """장부는 총량 하나만 센다. 20건이 소진됐을 때 "스윕이 먹었나 채팅이
    먹었나"를 답할 수 있는 출처는 이 로그뿐이다."""
    monkeypatch.setattr(call_budget, "DAILY_TOTAL", 20)
    monkeypatch.setattr(call_budget, "RESERVE", 12)
    _set_used(db_session, 4)

    with caplog.at_level(logging.INFO):
        assert call_budget.claim(db_session, "sweep") is True

    granted = [r for r in caplog.records if getattr(r, "event", "") == "ai_budget.claim.granted"]
    assert len(granted) == 1
    assert granted[0].levelname == "INFO"
    assert granted[0].consumer == "sweep"
    assert granted[0].used == 5
    assert granted[0].total == 20
    # 포매터가 없어 extra는 출력에 안 나온다. 사람이 읽는 줄에도 실려야 한다.
    assert "sweep" in granted[0].getMessage()


def test_장부를_새로_만든_선점도_남긴다(client, db_session, monkeypatch, caplog):
    """오늘 첫 호출은 UPDATE가 아니라 INSERT 경로로 간다. 경로마다 따로 적으면
    한쪽이 빠지고, 빠진 쪽이 하루의 첫 건이다."""
    monkeypatch.setattr(call_budget, "DAILY_TOTAL", 20)
    monkeypatch.setattr(call_budget, "RESERVE", 12)

    with caplog.at_level(logging.INFO):
        assert call_budget.claim(db_session, "user") is True

    granted = [r for r in caplog.records if getattr(r, "event", "") == "ai_budget.claim.granted"]
    assert [(r.consumer, r.used) for r in granted] == [("user", 1)]


def test_거절된_선점은_성공으로_남지_않는다(client, db_session, monkeypatch, caplog):
    """거절을 성공으로 세면 집계가 실제 소비보다 커진다."""
    monkeypatch.setattr(call_budget, "DAILY_TOTAL", 20)
    monkeypatch.setattr(call_budget, "RESERVE", 12)
    _set_used(db_session, 20)

    with caplog.at_level(logging.INFO):
        assert call_budget.claim(db_session, "user") is False

    assert not [r for r in caplog.records if getattr(r, "event", "") == "ai_budget.claim.granted"]
