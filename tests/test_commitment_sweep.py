from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from sqlalchemy import select

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


def _make_room(db_session, group_id, message_count, created_by, name="A사 방"):
    """ChatRoom.created_by도 NOT NULL FK라 채워야 한다.

    ChatMessage는 group_id 컬럼이 아예 없다(Task 1이 의도적으로 뺐다 — 그룹은
    room_id를 통해서만 안다). 여기서 group_id를 넘기지 않는다.

    메시지 본문에 방 이름을 넣어두면, 방마다 다르게 동작하는 스텁을 만들 때
    "N번째로 처리된 방"이 아니라 "어떤 방인지"로 분기할 수 있어 쿼리 순서에
    의존하지 않는 테스트를 짤 수 있다.
    """
    room = ChatRoom(group_id=group_id, name=name, created_by=created_by)
    db_session.add(room)
    db_session.commit()
    db_session.refresh(room)
    for i in range(message_count):
        db_session.add(
            ChatMessage(
                room_id=room.id,
                sender="김담당",
                content=f"[{name}] 메시지 {i}",
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
    room = _make_room(db_session, group.id, message_count=20, created_by=group.created_by)

    def boom(text):
        raise RuntimeError("모델 폭발")

    monkeypatch.setattr(commitment_service.gemini_service, "extract_chat_commitments", boom)

    assert commitment_service.maybe_sweep(db_session, group.id) == 0

    # 방은 실패했어도 시도 자체는 기록돼야 한다 — 안 그러면 쿨다운이 무력화돼
    # 매 요청마다 이 그룹 전체를 다시 스캔 시도하게 된다.
    db_session.refresh(group)
    assert group.last_swept_at is not None
    db_session.refresh(room)
    assert room.last_scanned_message_id is None


def test_sweep_isolates_room_failure_from_other_rooms(client, db_session, monkeypatch):
    """방 하나가 터져도 다른 방의 결과는 살아남는다.

    한 트랜잭션에 전체 방 순회를 묶으면, 방 B의 실패가 이미 처리된 방 A의
    커밋되지 않은 결과까지 롤백시킨다. 방마다 독립적으로 커밋해야 한다.
    """
    group = _seed_group(client, db_session)
    room_ok = _make_room(
        db_session, group.id, message_count=20, created_by=group.created_by, name="정상방"
    )
    room_bad = _make_room(
        db_session, group.id, message_count=20, created_by=group.created_by, name="폭발방"
    )

    def fake_extract(text):
        if "폭발방" in text:
            raise RuntimeError("방 폭발")
        return _SAMPLE

    mock = MagicMock(side_effect=fake_extract)
    monkeypatch.setattr(commitment_service.gemini_service, "extract_chat_commitments", mock)

    scanned = commitment_service.maybe_sweep(db_session, group.id)

    assert scanned == 1
    assert mock.call_count == 2

    db_session.refresh(room_ok)
    db_session.refresh(room_bad)
    assert room_ok.last_scanned_message_id is not None
    assert room_bad.last_scanned_message_id is None

    saved = db_session.query(Commitment).all()
    assert len(saved) == 1
    assert saved[0].content == "시안 전달"

    # 실패한 방이 있어도 시도 자체는 기록되어 쿨다운이 정상 작동해야 한다.
    db_session.refresh(group)
    assert group.last_swept_at is not None


def test_sweep_does_not_advance_pointer_on_extraction_failure(client, db_session, monkeypatch):
    """extract_chat_commitments가 None(실패)을 돌려주면 포인터를 전진시키지 않는다.

    실패를 빈 배열과 뭉뚱그리면 그 배치에 실제로 있던 약속이 영원히
    다시 검사되지 않는다.
    """
    group = _seed_group(client, db_session)
    room = _make_room(db_session, group.id, message_count=20, created_by=group.created_by)
    _stub_extractor(monkeypatch, None)

    scanned = commitment_service.maybe_sweep(db_session, group.id)

    assert scanned == 0
    db_session.refresh(room)
    assert room.last_scanned_message_id is None
    assert db_session.query(Commitment).count() == 0


def test_sweep_advances_pointer_on_genuinely_empty_result(client, db_session, monkeypatch):
    """extract_chat_commitments가 빈 리스트(진짜 약속 없음)를 돌려주면 포인터는 전진한다.

    실패(None)와 구분되는 정상 결과다 — 저장할 약속은 없어도 스캔 자체는
    성공했으므로 같은 배치를 다시 검사할 필요가 없다.
    """
    group = _seed_group(client, db_session)
    room = _make_room(db_session, group.id, message_count=20, created_by=group.created_by)
    _stub_extractor(monkeypatch, [])

    scanned = commitment_service.maybe_sweep(db_session, group.id)

    assert scanned == 1
    db_session.refresh(room)
    assert room.last_scanned_message_id is not None
    assert db_session.query(Commitment).count() == 0


def test_sweep_caps_messages_per_scan(client, db_session, monkeypatch):
    """방 하나에 상한을 넘는 메시지가 쌓여도 상한만큼만 처리하고,

    나머지는 다음 스윕이 이어받는다. 상한이 없으면 토큰 한도로 실패하고,
    실패 시 포인터를 전진시키지 않으므로 그 방은 영원히 같은 실패를
    반복하게 된다.
    """
    group = _seed_group(client, db_session)
    total = commitment_service.CHAT_SCAN_BATCH_LIMIT + 20
    room = _make_room(db_session, group.id, message_count=total, created_by=group.created_by)
    mock = _stub_extractor(monkeypatch, _SAMPLE)

    scanned = commitment_service.maybe_sweep(db_session, group.id)

    assert scanned == 1
    mock.assert_called_once()
    history_arg = mock.call_args[0][0]
    assert len(history_arg.splitlines()) == commitment_service.CHAT_SCAN_BATCH_LIMIT

    all_messages = (
        db_session.execute(
            select(ChatMessage).where(ChatMessage.room_id == room.id).order_by(ChatMessage.id)
        )
        .scalars()
        .all()
    )
    db_session.refresh(room)
    assert room.last_scanned_message_id == all_messages[commitment_service.CHAT_SCAN_BATCH_LIMIT - 1].id

    # 두 번째 스윕(쿨다운 해제)이 나머지를 이어받는지
    mock.reset_mock()
    group.last_swept_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.commit()

    scanned_again = commitment_service.maybe_sweep(db_session, group.id)

    assert scanned_again == 1
    mock.assert_called_once()
    db_session.refresh(room)
    assert room.last_scanned_message_id == all_messages[-1].id


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


def test_list_endpoint_survives_sweep_failure_with_existing_data_intact(
    client, db_session, monkeypatch
):
    """스윕이 터져도 조회는 200과 기존 데이터를 온전히 돌려줘야 한다.

    maybe_sweep 단위 테스트만으로는 부족하다 — db.rollback()이 이번 요청의
    조회 결과까지 비워버리는 종류의 버그는 상태 코드만 봐서는 안 잡힌다.
    """
    signup = client.post(
        "/api/v1/auth/signup",
        json={"email": "admin@onque.dev", "password": "password123", "name": "관리자"},
    ).json()["data"]
    token = signup["token"]
    admin_id = signup["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}
    group = client.post("/api/v1/groups", json={"name": "A팀"}, headers=headers).json()["data"]

    existing = Commitment(
        group_id=group["id"],
        client_id=None,
        content="기존 약속",
        due_date=None,
        status="proposed",
        source_type="call",
        source_id=None,
        evidence="이미 있던 근거",
    )
    db_session.add(existing)
    db_session.commit()

    _make_room(db_session, group["id"], message_count=20, created_by=admin_id)

    def boom(text):
        raise RuntimeError("모델 폭발")

    monkeypatch.setattr(commitment_service.gemini_service, "extract_chat_commitments", boom)

    res = client.get("/api/v1/commitments", params={"group_id": group["id"]}, headers=headers)

    assert res.status_code == 200
    assert [c["content"] for c in res.json()["data"]] == ["기존 약속"]
