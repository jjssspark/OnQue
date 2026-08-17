from datetime import date, datetime, timedelta, timezone

from models import ChatRoom, ChatRoomMember, Client, Commitment, Group, User


def _setup(client):
    token = client.post(
        "/api/v1/auth/signup",
        json={"email": "admin@onque.dev", "password": "password123", "name": "관리자"},
    ).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    group_a = client.post("/api/v1/groups", json={"name": "A팀"}, headers=headers).json()["data"]
    group_b = client.post("/api/v1/groups", json={"name": "B팀"}, headers=headers).json()["data"]
    return headers, group_a["id"], group_b["id"]


def _seed(db_session, group_id, **kwargs):
    defaults = {
        "group_id": group_id,
        "content": "시안 3종 전달",
        "source_type": "call",
        "evidence": "수요일까지 드릴게요",
    }
    defaults.update(kwargs)
    c = Commitment(**defaults)
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


def test_list_returns_client_name(client, db_session):
    headers, group_a, _ = _setup(client)
    a = Client(group_id=group_a, name="A사")
    db_session.add(a)
    db_session.commit()
    _seed(db_session, group_a, client_id=a.id)

    res = client.get("/api/v1/commitments", params={"group_id": group_a}, headers=headers)
    data = res.json()["data"]
    assert len(data) == 1
    assert data[0]["client_name"] == "A사"
    assert data[0]["status"] == "proposed"


def test_list_filters_by_status(client, db_session):
    headers, group_a, _ = _setup(client)
    _seed(db_session, group_a, content="제안된 것")
    _seed(db_session, group_a, content="확정된 것", status="confirmed")

    res = client.get(
        "/api/v1/commitments",
        params={"group_id": group_a, "status": "proposed"},
        headers=headers,
    )
    assert [c["content"] for c in res.json()["data"]] == ["제안된 것"]


def test_list_isolated_between_groups(client, db_session):
    headers, group_a, group_b = _setup(client)
    _seed(db_session, group_b, content="B팀 약속")

    res = client.get("/api/v1/commitments", params={"group_id": group_a}, headers=headers)
    assert res.json()["data"] == []


def test_list_meta_reports_total_limit_and_has_next(client, db_session):
    headers, group_a, _ = _setup(client)
    for i in range(3):
        _seed(db_session, group_a, content=f"약속 {i}")

    res = client.get(
        "/api/v1/commitments",
        params={"group_id": group_a, "limit": 2},
        headers=headers,
    )
    meta = res.json()["meta"]
    assert (meta["total"], meta["limit"], meta["hasNext"]) == (3, 2, True)
    assert len(res.json()["data"]) == 2


def test_list_meta_has_next_false_when_everything_fits(client, db_session):
    headers, group_a, _ = _setup(client)
    _seed(db_session, group_a, content="유일한 약속")

    res = client.get(
        "/api/v1/commitments", params={"group_id": group_a}, headers=headers
    )
    meta = res.json()["meta"]
    assert (meta["total"], meta["limit"], meta["hasNext"]) == (1, 20, False)


def test_list_meta_reports_sweep_never_run(client, db_session):
    """한 번도 안 돌았으면 last_at이 None이다. 0이 아니라 None인 이유는
    "0개 찾음"과 "아직 안 돌아봄"이 화면에서 달리 보여야 하기 때문이다."""
    headers, group_a, _ = _setup(client)
    _seed(db_session, group_a)

    res = client.get("/api/v1/commitments", params={"group_id": group_a}, headers=headers)
    sweep = res.json()["meta"]["sweep"]
    assert sweep["last_at"] is None
    assert sweep["scanned"] is None
    assert sweep["found"] is None


def test_list_meta_reports_last_sweep_result(client, db_session):
    headers, group_a, _ = _setup(client)
    _seed(db_session, group_a)
    swept_at = datetime(2026, 8, 16, 3, 0, tzinfo=timezone.utc)
    group = db_session.get(Group, group_a)
    group.last_scan_at = swept_at
    group.last_sweep_scanned = 34
    group.last_sweep_found = 2
    db_session.commit()

    res = client.get("/api/v1/commitments", params={"group_id": group_a}, headers=headers)
    sweep = res.json()["meta"]["sweep"]
    assert sweep["last_at"] == swept_at.isoformat()
    assert sweep["scanned"] == 34
    assert sweep["found"] == 2


def test_list_exposes_room_id(client, db_session):
    """약속 카드에서 출처 대화방으로 건너뛰려면 room_id가 필요하다.
    가시성은 이미 room_id로 걸러진 뒤라 여기서 내려도 새지 않는다."""
    headers, group_a, _ = _setup(client)
    admin = db_session.query(User).filter_by(email="admin@onque.dev").one()
    room = ChatRoom(group_id=group_a, name="영업방", created_by=admin.id)
    db_session.add(room)
    db_session.commit()
    db_session.refresh(room)

    # 목록을 조회하는 사람이 방 멤버여야 채팅 출처 약속이 보인다.
    db_session.add(ChatRoomMember(room_id=room.id, user_id=admin.id))
    db_session.commit()

    _seed(db_session, group_a, source_type="chat", room_id=room.id)
    _seed(db_session, group_a, content="전화 약속")

    res = client.get("/api/v1/commitments", params={"group_id": group_a}, headers=headers)
    by_content = {c["content"]: c["room_id"] for c in res.json()["data"]}
    assert by_content["시안 3종 전달"] == room.id
    assert by_content["전화 약속"] is None


def test_list_rejects_limit_over_100(client, db_session):
    headers, group_a, _ = _setup(client)
    res = client.get(
        "/api/v1/commitments", params={"group_id": group_a, "limit": 500}, headers=headers
    )
    assert res.status_code == 422


def test_due_soon_and_overdue_are_computed(client, db_session):
    headers, group_a, _ = _setup(client)
    today = date.today()
    _seed(
        db_session, group_a, content="지남", status="confirmed",
        due_date=today - timedelta(days=1),
    )
    _seed(
        db_session, group_a, content="임박", status="confirmed",
        due_date=today + timedelta(days=1),
    )
    _seed(
        db_session, group_a, content="여유", status="confirmed",
        due_date=today + timedelta(days=30),
    )
    # proposed는 아직 추적 대상이 아니므로 경고하지 않는다
    _seed(db_session, group_a, content="제안", due_date=today - timedelta(days=5))

    data = client.get(
        "/api/v1/commitments", params={"group_id": group_a}, headers=headers
    ).json()["data"]
    by_content = {c["content"]: c for c in data}

    assert by_content["지남"]["is_overdue"] is True
    assert by_content["임박"]["is_due_soon"] is True
    assert by_content["여유"]["is_due_soon"] is False
    assert by_content["제안"]["is_overdue"] is False


def test_patch_confirms_commitment(client, db_session):
    headers, group_a, _ = _setup(client)
    c = _seed(db_session, group_a)

    res = client.patch(
        f"/api/v1/commitments/{c.id}", json={"status": "confirmed"}, headers=headers
    )
    assert res.status_code == 200
    assert res.json()["data"]["status"] == "confirmed"

    db_session.expire_all()
    assert db_session.get(Commitment, c.id).confirmed_at is not None


def test_patch_rejects_transition_from_terminal_status(client, db_session):
    headers, group_a, _ = _setup(client)
    c = _seed(db_session, group_a, status="dismissed")

    res = client.patch(
        f"/api/v1/commitments/{c.id}", json={"status": "confirmed"}, headers=headers
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "COMMITMENT_STATUS_INVALID"


def test_patch_rejects_skipping_confirmation(client, db_session):
    """proposed에서 confirmed를 건너뛰고 fulfilled로 가면 승인 게이트가 무력화된다."""
    headers, group_a, _ = _setup(client)
    c = _seed(db_session, group_a)

    res = client.patch(
        f"/api/v1/commitments/{c.id}", json={"status": "fulfilled"}, headers=headers
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "COMMITMENT_STATUS_INVALID"

    db_session.expire_all()
    assert db_session.get(Commitment, c.id).status == "proposed"


def test_patch_rejects_undoing_confirmation(client, db_session):
    """confirmed를 proposed로 되돌리는 것도 허용하지 않는다 — 되돌리기는 없다."""
    headers, group_a, _ = _setup(client)
    c = _seed(db_session, group_a, status="confirmed")

    res = client.patch(
        f"/api/v1/commitments/{c.id}", json={"status": "proposed"}, headers=headers
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "COMMITMENT_STATUS_INVALID"

    db_session.expire_all()
    assert db_session.get(Commitment, c.id).status == "confirmed"


def test_patch_allows_remaining_valid_transitions(client, db_session):
    """proposed->confirmed는 test_patch_confirms_commitment가 이미 덮는다.
    나머지 허용 전이(proposed->dismissed, confirmed->fulfilled, confirmed->dismissed)를
    확인한다."""
    headers, group_a, _ = _setup(client)
    to_dismiss = _seed(db_session, group_a, content="첫째")
    to_fulfill = _seed(db_session, group_a, content="둘째", status="confirmed")
    confirmed_to_dismiss = _seed(db_session, group_a, content="셋째", status="confirmed")

    res1 = client.patch(
        f"/api/v1/commitments/{to_dismiss.id}", json={"status": "dismissed"}, headers=headers
    )
    res2 = client.patch(
        f"/api/v1/commitments/{to_fulfill.id}", json={"status": "fulfilled"}, headers=headers
    )
    res3 = client.patch(
        f"/api/v1/commitments/{confirmed_to_dismiss.id}",
        json={"status": "dismissed"},
        headers=headers,
    )

    assert res1.status_code == 200
    assert res2.status_code == 200
    assert res3.status_code == 200

    db_session.expire_all()
    assert db_session.get(Commitment, to_dismiss.id).status == "dismissed"
    assert db_session.get(Commitment, to_fulfill.id).status == "fulfilled"
    assert db_session.get(Commitment, confirmed_to_dismiss.id).status == "dismissed"


def test_patch_rejects_unknown_status(client, db_session):
    headers, group_a, _ = _setup(client)
    c = _seed(db_session, group_a)

    res = client.patch(
        f"/api/v1/commitments/{c.id}", json={"status": "잘못된값"}, headers=headers
    )
    assert res.status_code == 400


def test_patch_rejects_cross_group(client, db_session):
    headers, group_a, _ = _setup(client)
    other = client.post(
        "/api/v1/auth/signup",
        json={"email": "other@onque.dev", "password": "password123", "name": "외부인"},
    ).json()["data"]["token"]
    c = _seed(db_session, group_a)

    res = client.patch(
        f"/api/v1/commitments/{c.id}",
        json={"status": "confirmed"},
        headers={"Authorization": f"Bearer {other}"},
    )
    assert res.status_code == 403


def test_bulk_status_rejects_all_if_transition_invalid(client, db_session):
    """일괄 요청에 확정을 건너뛰는 전이가 하나라도 섞이면 전체를 거부하고
    아무것도 바꾸지 않는다. can_transition을 공유하므로 단일 PATCH와 같은
    규칙이 적용돼야 한다."""
    headers, group_a, _ = _setup(client)
    valid = _seed(db_session, group_a, content="유효", status="confirmed")
    invalid = _seed(db_session, group_a, content="무효")  # proposed, fulfilled로 못 감

    res = client.post(
        "/api/v1/commitments/bulk-status",
        json={"ids": [valid.id, invalid.id], "status": "fulfilled"},
        headers=headers,
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "COMMITMENT_STATUS_INVALID"

    db_session.expire_all()
    assert db_session.get(Commitment, valid.id).status == "confirmed"
    assert db_session.get(Commitment, invalid.id).status == "proposed"


def test_bulk_status_confirms_many(client, db_session):
    headers, group_a, _ = _setup(client)
    a = _seed(db_session, group_a, content="첫째")
    b = _seed(db_session, group_a, content="둘째")

    res = client.post(
        "/api/v1/commitments/bulk-status",
        json={"ids": [a.id, b.id], "status": "confirmed"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["data"]["updated"] == 2

    db_session.expire_all()
    assert db_session.get(Commitment, a.id).status == "confirmed"
    assert db_session.get(Commitment, b.id).status == "confirmed"


def test_bulk_status_rejects_over_100_ids(client, db_session):
    headers, group_a, _ = _setup(client)
    res = client.post(
        "/api/v1/commitments/bulk-status",
        json={"ids": list(range(1, 102)), "status": "confirmed"},
        headers=headers,
    )
    assert res.status_code == 422


def test_bulk_status_dedupes_repeated_ids(client, db_session):
    """ids=[1, 1]을 보내면 updated가 1이어야 한다. 중복을 그대로 두면
    존재 확인(len(rows) != len(ids))에서 어긋나거나 카운트가 호출자의
    기대와 달라진다."""
    headers, group_a, _ = _setup(client)
    a = _seed(db_session, group_a, content="하나")

    res = client.post(
        "/api/v1/commitments/bulk-status",
        json={"ids": [a.id, a.id], "status": "confirmed"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["data"]["updated"] == 1

    db_session.expire_all()
    assert db_session.get(Commitment, a.id).status == "confirmed"


def test_bulk_status_rejects_all_if_one_is_foreign(client, db_session):
    """부분 성공은 사용자가 무엇이 반영됐는지 알 수 없게 만든다. 전부 거부한다.

    브리프 원문은 outsider가 POST /groups로 직접 그룹을 만들지만, 그룹 생성은
    admin 역할만 가능하고(routers/groups.py `_require_admin`) admin은 이 테스트
    DB에서 가장 먼저 가입한 사용자만 된다. 여기서는 admin@onque.dev가 이미
    먼저 가입했으므로 outsider는 member가 되어 그룹을 만들 수 없다(403).
    테스트가 검증하려는 건 "남의 그룹이 섞이면 전체 거부"이지 그 그룹이
    API로 만들어졌는지가 아니므로, db_session으로 직접 시딩한다.
    """
    headers, group_a, _ = _setup(client)
    outsider_id = client.post(
        "/api/v1/auth/signup",
        json={"email": "out@onque.dev", "password": "password123", "name": "외부인"},
    ).json()["data"]["user"]["id"]

    foreign_group = Group(name="외부팀", created_by=outsider_id)
    db_session.add(foreign_group)
    db_session.commit()
    db_session.refresh(foreign_group)

    mine = _seed(db_session, group_a, content="내 것")
    theirs = _seed(db_session, foreign_group.id, content="남의 것")

    res = client.post(
        "/api/v1/commitments/bulk-status",
        json={"ids": [mine.id, theirs.id], "status": "dismissed"},
        headers=headers,
    )
    assert res.status_code == 403

    db_session.expire_all()
    assert db_session.get(Commitment, mine.id).status == "proposed"
