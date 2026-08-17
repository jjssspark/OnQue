from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from sqlalchemy import select

import call_budget
import commitment_service
import gemini_service
from models import ChatMessage, ChatRoom, ChatRoomMember, Commitment, Group


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
    # 실제 방 생성 API(main.py의 create_chat_room)는 만든 사람을
    # ChatRoomMember로 함께 넣는다. 여기서도 그래야 room-membership 가시성
    # 필터(commitment_service.visible_commitment_filter) 아래에서
    # created_by 본인이 자기가 만든 방에서 나온 약속을 못 보는 비현실적인
    # 상태가 되지 않는다.
    db_session.add(ChatRoomMember(room_id=room.id, user_id=created_by))
    db_session.commit()
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

    def gated(history_text, *, claim):
        # 진짜 함수와 같은 순서로 문을 지난다. 스텁이 예산을 건너뛰면
        # 예산 테스트가 아무것도 검사하지 못한 채 초록으로 남는다.
        if not claim():
            raise gemini_service.QuotaExceeded
        return mock(history_text)

    monkeypatch.setattr(commitment_service.gemini_service, "extract_chat_commitments", gated)
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
    # 이 단언이 없으면 room_id를 채우는 한 줄을 지워도 스위트가 전부 통과한다.
    # 그 상태로 배포되면 모든 채팅 약속이 "방이 삭제됨"으로 오판돼
    # 비공개 방 대화 원문이 그룹 전원에게 공개된다.
    assert saved[0].room_id == room.id

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

    def boom(text, **kwargs):
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

    def fake_extract(text, **kwargs):
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


def test_concurrent_sweep_second_caller_loses_to_the_first(client, db_session, monkeypatch):
    """스윕 도중(Gemini 호출 시점)에 다른 요청이 같은 그룹을 스윕하려 하면
    쿨다운 선점 때문에 즉시 0을 반환해야 한다 — 안 그러면 두 요청이 같은
    배치에 Gemini를 두 번 부르고 같은 약속을 중복 저장한다(유니크 제약 없음).

    진짜 스레드 동시성 대신, extractor 실행 도중 별도 세션으로 maybe_sweep을
    재호출해 "겹치는 요청"을 결정론적으로 재현한다. 쿨다운 선점 UPDATE가
    Gemini 호출보다 먼저 커밋돼 있어야만 두 번째 호출이 진입 즉시 막힌다.
    """
    from tests.conftest import TestSessionLocal

    group = _seed_group(client, db_session)
    _make_room(db_session, group.id, message_count=20, created_by=group.created_by)

    second_call_result = {}

    def extractor_that_races(text, **kwargs):
        concurrent_session = TestSessionLocal()
        try:
            second_call_result["scanned"] = commitment_service.maybe_sweep(
                concurrent_session, group.id
            )
        finally:
            concurrent_session.close()
        return _SAMPLE

    monkeypatch.setattr(
        commitment_service.gemini_service, "extract_chat_commitments", extractor_that_races
    )

    first_scanned = commitment_service.maybe_sweep(db_session, group.id)

    assert first_scanned == 1
    assert second_call_result["scanned"] == 0
    # 중복 저장되지 않았는지도 함께 확인한다.
    assert db_session.query(Commitment).count() == 1


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

    def boom(text, **kwargs):
        raise RuntimeError("모델 폭발")

    monkeypatch.setattr(commitment_service.gemini_service, "extract_chat_commitments", boom)

    res = client.get("/api/v1/commitments", params={"group_id": group["id"]}, headers=headers)

    assert res.status_code == 200
    assert [c["content"] for c in res.json()["data"]] == ["기존 약속"]


# ── 일일 예산 가드 ────────────────────────────────────────────
#
# 스윕은 사용자가 시키지 않았는데 도는 백그라운드 작업이고, Gemini 무료 티어
# 하루 20건을 사용자가 직접 올리는 파일 요약과 나눠 쓴다. 예산이 없으면
# 오전 채팅이 한도를 다 먹고, 오후에 회의 녹음을 올린 사람이 "한도 소진"을
# 본다. 시킨 일이 안 시킨 일 때문에 실패하는 것이 한도 자체보다 나쁘다.


def _set_budget(monkeypatch, limit):
    """스윕 상한은 총량 - 예비선이다. 예비선을 0으로 두고 총량으로 상한을 잡는다."""
    monkeypatch.setattr(call_budget, "DAILY_TOTAL", limit)
    monkeypatch.setattr(call_budget, "RESERVE", 0)


def test_예산이_남아있으면_평소대로_스캔한다(client, db_session, monkeypatch):
    _set_budget(monkeypatch, 8)
    group = _seed_group(client, db_session)
    _make_room(db_session, group.id, message_count=15, created_by=group.created_by)
    mock = _stub_extractor(monkeypatch, _SAMPLE)

    assert commitment_service.maybe_sweep(db_session, group.id) == 1
    mock.assert_called_once()


def test_예산을_다_쓰면_Gemini를_부르지_않는다(client, db_session, monkeypatch):
    _set_budget(monkeypatch, 1)
    group = _seed_group(client, db_session)
    _make_room(db_session, group.id, message_count=15, created_by=group.created_by)
    mock = _stub_extractor(monkeypatch, _SAMPLE)

    # 1회차: 예산 1건을 쓴다
    assert commitment_service.maybe_sweep(db_session, group.id) == 1
    assert mock.call_count == 1

    # 2회차: 쿨다운을 풀어 스윕은 돌게 하되, 예산이 없어 호출은 막혀야 한다
    group.last_swept_at = None
    db_session.commit()
    _make_room(
        db_session, group.id, message_count=15,
        created_by=group.created_by, name="B사 방",
    )

    assert commitment_service.maybe_sweep(db_session, group.id) == 0
    assert mock.call_count == 1, "예산이 소진됐는데 Gemini를 또 불렀다"


def test_기준_미만인_방은_예산을_쓰지_않는다(client, db_session, monkeypatch):
    """14개짜리 방을 훑는 시늉만 하고 예산을 깎으면, 정작 대화가 쌓인 방이
    호출할 몫을 한산한 방들이 먼저 먹어치운다."""
    _set_budget(monkeypatch, 1)
    group = _seed_group(client, db_session)
    _make_room(db_session, group.id, message_count=14, created_by=group.created_by)
    mock = _stub_extractor(monkeypatch, _SAMPLE)

    assert commitment_service.maybe_sweep(db_session, group.id) == 0
    mock.assert_not_called()
    assert call_budget.used_today(db_session) == 0


def test_예산은_그룹이_아니라_전체_공유다(client, db_session, monkeypatch):
    """Gemini 한도는 API 키 하나에 걸린다. 그룹마다 예산을 따로 주면
    그룹 수만큼 한도를 넘긴다."""
    _set_budget(monkeypatch, 1)
    group_a = _seed_group(client, db_session, name="A팀")
    _make_room(db_session, group_a.id, message_count=15, created_by=group_a.created_by)
    group_b = Group(name="B팀", created_by=group_a.created_by)
    db_session.add(group_b)
    db_session.commit()
    db_session.refresh(group_b)
    _make_room(
        db_session, group_b.id, message_count=15,
        created_by=group_a.created_by, name="B사 방",
    )
    mock = _stub_extractor(monkeypatch, _SAMPLE)

    assert commitment_service.maybe_sweep(db_session, group_a.id) == 1
    assert commitment_service.maybe_sweep(db_session, group_b.id) == 0
    assert mock.call_count == 1


def test_추출_실패해도_예산은_소비된_채로_남는다(client, db_session, monkeypatch):
    """실패해도 Gemini 호출은 이미 나갔다. 예산을 되돌리면 실패하는 방이
    남은 예산을 전부 태우며 재시도를 반복한다."""
    _set_budget(monkeypatch, 8)
    group = _seed_group(client, db_session)
    _make_room(db_session, group.id, message_count=15, created_by=group.created_by)
    _stub_extractor(monkeypatch, None)

    assert commitment_service.maybe_sweep(db_session, group.id) == 0
    assert call_budget.used_today(db_session) == 1


# ── 스윕 결과 기록 ────────────────────────────────────────────
#
# 스윕은 조용히 돌아서 사용자가 AI가 일하고 있다는 걸 모른다. 언제 돌았는지는
# last_swept_at으로 알 수 있지만 "무엇을 얼마나 했는지"는 어디에도 남지 않는다.
# 화면에 "대화 34개에서 2건 찾음"을 띄우려면 그 두 숫자가 필요하다.


def test_스캔한_메시지와_찾은_약속_수를_남긴다(client, db_session, monkeypatch):
    group = _seed_group(client, db_session)
    _make_room(db_session, group.id, message_count=20, created_by=group.created_by)
    _stub_extractor(monkeypatch, _SAMPLE)

    commitment_service.maybe_sweep(db_session, group.id)

    db_session.refresh(group)
    assert group.last_sweep_scanned == 20
    assert group.last_sweep_found == 1


def test_여러_방을_훑으면_합계를_남긴다(client, db_session, monkeypatch):
    group = _seed_group(client, db_session)
    _make_room(db_session, group.id, message_count=15, created_by=group.created_by)
    _make_room(
        db_session, group.id, message_count=20,
        created_by=group.created_by, name="B사 방",
    )
    _stub_extractor(monkeypatch, _SAMPLE)

    commitment_service.maybe_sweep(db_session, group.id)

    db_session.refresh(group)
    assert group.last_sweep_scanned == 35
    assert group.last_sweep_found == 2


def test_훑을_게_없으면_직전_기록을_지우지_않는다(client, db_session, monkeypatch):
    """0으로 덮어쓰면 "방금 아무것도 못 찾음"과 "10분간 새 대화가 없음"이
    화면에서 같아 보인다. 뒤쪽이면 직전 성과를 계속 보여주는 게 맞다."""
    group = _seed_group(client, db_session)
    _make_room(db_session, group.id, message_count=15, created_by=group.created_by)
    _stub_extractor(monkeypatch, _SAMPLE)

    commitment_service.maybe_sweep(db_session, group.id)
    db_session.refresh(group)
    assert group.last_sweep_scanned == 15

    # 새 메시지 없이 쿨다운만 풀고 다시 돌린다
    group.last_swept_at = None
    db_session.commit()
    commitment_service.maybe_sweep(db_session, group.id)

    db_session.refresh(group)
    assert group.last_sweep_scanned == 15, "훑은 게 없는데 기록이 0으로 덮였다"
    assert group.last_sweep_found == 1


def test_약속을_못_찾아도_훑은_사실은_남긴다(client, db_session, monkeypatch):
    """대화는 읽었는데 약속이 없었던 것과, 아예 안 읽은 것은 다르다."""
    group = _seed_group(client, db_session)
    _make_room(db_session, group.id, message_count=18, created_by=group.created_by)
    _stub_extractor(monkeypatch, [])

    commitment_service.maybe_sweep(db_session, group.id)

    db_session.refresh(group)
    assert group.last_sweep_scanned == 18
    assert group.last_sweep_found == 0
