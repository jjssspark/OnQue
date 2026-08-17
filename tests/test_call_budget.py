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
