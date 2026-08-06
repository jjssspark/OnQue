from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from models import Client, Commitment


def test_client_name_unique_per_group(client, db_session):
    db_session.add(Client(group_id=1, name="A사"))
    db_session.commit()

    db_session.add(Client(group_id=1, name="A사"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_same_client_name_allowed_in_other_group(client, db_session):
    db_session.add(Client(group_id=1, name="A사"))
    db_session.add(Client(group_id=2, name="A사"))
    db_session.commit()

    assert db_session.query(Client).count() == 2


def test_commitment_defaults_to_proposed(client, db_session):
    c = Commitment(
        group_id=1,
        content="시안 3종 전달",
        source_type="call",
        evidence="다음 주 수요일까지 시안 세 개 보내드릴게요",
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)

    assert c.status == "proposed"
    assert c.client_id is None
    assert c.due_date is None
    assert c.confirmed_at is None


def test_commitment_rejects_unknown_status(client, db_session):
    db_session.add(
        Commitment(
            group_id=1,
            content="시안 전달",
            source_type="call",
            evidence="보내드릴게요",
            status="unknown",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_commitment_accepts_due_date_and_client(client, db_session):
    a = Client(group_id=1, name="A사")
    db_session.add(a)
    db_session.commit()

    c = Commitment(
        group_id=1,
        client_id=a.id,
        content="시안 3종 전달",
        due_date=date(2026, 8, 13),
        source_type="chat",
        source_id=42,
        evidence="수요일까지 드릴게요",
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)

    assert c.client_id == a.id
    assert c.due_date == date(2026, 8, 13)
