from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import commitment_service
from models import ChatMessage, ChatRoom, Commitment, Group


def _seed_group(client, db_session, name="A팀", **group_kwargs):
    """관리자 유저를 만들고 그 id로 Group.created_by를 채운다.

    Group.created_by는 NOT NULL FK라 브리프 원문처럼 이름만으로 만들 수 없다.
    같은 브랜치의 tests/test_commitment_routes.py:271 관례(신가입 유저 id를
    created_by에 넘김)를 그대로 따른다.
    """
    admin_id = client.post(
        "/api/v1/auth/signup",
        json={"email": "admin@onque.dev", "password": "password123", "name": "관리자"},
    ).json()["data"]["user"]["id"]
    group = Group(name=name, created_by=admin_id, **group_kwargs)
    db_session.add(group)
    db_session.commit()
    db_session.refresh(group)
    return group


def _make_room(db_session, group_id, message_count, created_by):
    """ChatRoom.created_by도 NOT NULL FK라 채워야 한다.

    ChatMessage는 group_id 컬럼이 아예 없다(Task 1이 의도적으로 뺐다 — 그룹은
    room_id를 통해서만 안다). 여기서 group_id를 넘기지 않는다.
    """
    room = ChatRoom(group_id=group_id, name="A사 방", created_by=created_by)
    db_session.add(room)
    db_session.commit()
    db_session.refresh(room)
    for i in range(message_count):
        db_session.add(
            ChatMessage(
                room_id=room.id,
                sender="김담당",
                content=f"메시지 {i}",
            )
        )
    db_session.commit()
    return room


def _stub_extractor(monkeypatch, items):
    """호출 여부까지 검증할 수 있도록 MagicMock으로 스텁한다.

    응답 코드나 커밋 개수만으로는 "스캔이 실제로 안 돌았다"를 증명하지 못한다.
    쿨다운/임계값 테스트는 이 mock이 호출되지 않았음을 직접 단언해야 한다.
    """
    mock = MagicMock(return_value=items)
    monkeypatch.setattr(commitment_service.gemini_service, "extract_chat_commitments", mock)
    return mock


_SAMPLE = [{"content": "시안 전달", "client_name": "", "due_date": "", "evidence": "드릴게요"}]


def test_sweep_skips_room_below_threshold(client, db_session, monkeypatch):
    group = _seed_group(client, db_session)
    _make_room(db_session, group.id, message_count=14, created_by=group.created_by)
    mock = _stub_extractor(monkeypatch, _SAMPLE)

    scanned = commitment_service.maybe_sweep(db_session, group.id)

    assert scanned == 0
    assert db_session.query(Commitment).count() == 0
    mock.assert_not_called()


def test_sweep_scans_room_at_threshold(client, db_session, monkeypatch):
    group = _seed_group(client, db_session)
    room = _make_room(db_session, group.id, message_count=15, created_by=group.created_by)
    mock = _stub_extractor(monkeypatch, _SAMPLE)

    scanned = commitment_service.maybe_sweep(db_session, group.id)

    assert scanned == 1
    mock.assert_called_once()
    saved = db_session.query(Commitment).all()
    assert len(saved) == 1
    assert saved[0].source_type == "chat"
    assert saved[0].status == "proposed"

    db_session.refresh(room)
    assert room.last_scanned_message_id is not None


def test_sweep_respects_cooldown(client, db_session, monkeypatch):
    group = _seed_group(client, db_session, last_swept_at=datetime.now(timezone.utc))
    _make_room(db_session, group.id, message_count=20, created_by=group.created_by)
    mock = _stub_extractor(monkeypatch, _SAMPLE)

    assert commitment_service.maybe_sweep(db_session, group.id) == 0
    assert db_session.query(Commitment).count() == 0
    mock.assert_not_called()


def test_sweep_runs_after_cooldown_expires(client, db_session, monkeypatch):
    stale = datetime.now(timezone.utc) - timedelta(
        minutes=commitment_service.SWEEP_COOLDOWN_MINUTES + 1
    )
    group = _seed_group(client, db_session, last_swept_at=stale)
    _make_room(db_session, group.id, message_count=20, created_by=group.created_by)
    mock = _stub_extractor(monkeypatch, _SAMPLE)

    assert commitment_service.maybe_sweep(db_session, group.id) == 1
    mock.assert_called_once()


def test_second_sweep_does_not_rescan_same_messages(client, db_session, monkeypatch):
    group = _seed_group(client, db_session)
    _make_room(db_session, group.id, message_count=20, created_by=group.created_by)
    mock = _stub_extractor(monkeypatch, _SAMPLE)

    commitment_service.maybe_sweep(db_session, group.id)
    assert mock.call_count == 1
    mock.reset_mock()

    # 쿨다운을 강제로 만료시켜 두 번째 스윕을 허용한다
    group.last_swept_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.commit()

    assert commitment_service.maybe_sweep(db_session, group.id) == 0
    mock.assert_not_called()
    assert db_session.query(Commitment).count() == 1


def test_sweep_failure_does_not_raise(client, db_session, monkeypatch):
    """스윕은 부가 작업이다. 터져도 조회 요청을 실패시키지 않는다."""
    group = _seed_group(client, db_session)
    _make_room(db_session, group.id, message_count=20, created_by=group.created_by)

    def boom(text):
        raise RuntimeError("모델 폭발")

    monkeypatch.setattr(commitment_service.gemini_service, "extract_chat_commitments", boom)

    assert commitment_service.maybe_sweep(db_session, group.id) == 0


def test_list_endpoint_triggers_sweep(client, db_session, monkeypatch):
    signup = client.post(
        "/api/v1/auth/signup",
        json={"email": "admin@onque.dev", "password": "password123", "name": "관리자"},
    ).json()["data"]
    token = signup["token"]
    admin_id = signup["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}
    group = client.post("/api/v1/groups", json={"name": "A팀"}, headers=headers).json()["data"]

    _make_room(db_session, group["id"], message_count=20, created_by=admin_id)
    _stub_extractor(monkeypatch, _SAMPLE)

    res = client.get("/api/v1/commitments", params={"group_id": group["id"]}, headers=headers)

    assert res.status_code == 200
    assert [c["content"] for c in res.json()["data"]] == ["시안 전달"]
