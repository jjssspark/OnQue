from models import ChatRoomMember


def _signup(client, email, name):
    return client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "password123", "name": name},
    ).json()["data"]


def _user_id(client, headers) -> int:
    return client.get("/api/v1/me", headers=headers).json()["data"]["user"]["id"]


def _setup(client):
    admin = _signup(client, "admin@onque.dev", "관리자")
    token = admin["token"]
    group_id = client.post(
        "/api/v1/groups", json={"name": "A팀"}, headers={"Authorization": f"Bearer {token}"}
    ).json()["data"]["id"]
    return token, group_id


def test_group_creation_makes_a_default_room(client):
    token, group_id = _setup(client)

    rooms = client.get(
        "/chat/rooms", params={"group_id": group_id}, headers={"Authorization": f"Bearer {token}"}
    ).json()

    assert [r["name"] for r in rooms] == ["일반"]
    assert rooms[0]["last_message"] is None


def test_signup_first_user_gets_default_room(client):
    """가입만으로는 그룹이 생기지 않는다. 그룹을 만들어야 기본 방이 함께 생긴다."""
    admin = _signup(client, "first@onque.dev", "첫가입자")
    token = admin["token"]
    headers = {"Authorization": f"Bearer {token}"}
    group_id = client.post(
        "/api/v1/groups", json={"name": "첫팀"}, headers=headers
    ).json()["data"]["id"]

    rooms = client.get(
        "/chat/rooms",
        params={"group_id": group_id},
        headers=headers,
    ).json()
    assert [r["name"] for r in rooms] == ["일반"]


def test_create_room_and_list_shows_last_message(client):
    token, group_id = _setup(client)
    auth = {"Authorization": f"Bearer {token}"}

    room = client.post(
        "/chat/rooms", json={"group_id": group_id, "name": "디자인 리뷰"}, headers=auth
    ).json()
    assert room["name"] == "디자인 리뷰"

    client.post(
        "/chat/messages",
        params={"room_id": room["id"]},
        json={"sender": "관리자", "content": "시안 공유합니다"},
        headers=auth,
    )

    rooms = client.get("/chat/rooms", params={"group_id": group_id}, headers=auth).json()
    target = next(r for r in rooms if r["id"] == room["id"])
    assert target["last_message"]["content"] == "시안 공유합니다"
    # 메시지가 없는 기본 방은 미리보기가 비어 있어야 한다.
    assert next(r for r in rooms if r["name"] == "일반")["last_message"] is None


def test_create_room_rejects_blank_name(client):
    token, group_id = _setup(client)

    res = client.post(
        "/chat/rooms",
        json={"group_id": group_id, "name": "   "},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert res.status_code == 400
    assert res.json()["error"]["code"] == "CHAT_ROOM_NAME_REQUIRED"


def test_room_messages_reject_non_member(client):
    token, group_id = _setup(client)
    room = client.get(
        "/chat/rooms", params={"group_id": group_id}, headers={"Authorization": f"Bearer {token}"}
    ).json()[0]
    outsider = _signup(client, "other@onque.dev", "타인")

    res = client.get(
        "/chat/messages",
        params={"room_id": room["id"]},
        headers={"Authorization": f"Bearer {outsider['token']}"},
    )

    assert res.status_code == 403
    assert res.json()["error"]["code"] == "GROUP_ACCESS_FORBIDDEN"


def test_missing_room_returns_404(client):
    token, _ = _setup(client)

    res = client.get(
        "/chat/messages",
        params={"room_id": 9999},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert res.status_code == 404
    assert res.json()["error"]["code"] == "CHAT_ROOM_NOT_FOUND"


def test_delete_room_removes_its_messages(client):
    token, group_id = _setup(client)
    auth = {"Authorization": f"Bearer {token}"}
    room = client.post(
        "/chat/rooms", json={"group_id": group_id, "name": "임시방"}, headers=auth
    ).json()
    client.post(
        "/chat/messages",
        params={"room_id": room["id"]},
        json={"sender": "관리자", "content": "지워질 메시지"},
        headers=auth,
    )

    res = client.delete(f"/chat/rooms/{room['id']}", headers=auth)
    assert res.status_code == 200

    rooms = client.get("/chat/rooms", params={"group_id": group_id}, headers=auth).json()
    assert room["id"] not in [r["id"] for r in rooms]


def test_delete_room_forbidden_for_other_member(client):
    token, group_id = _setup(client)
    auth = {"Authorization": f"Bearer {token}"}
    room = client.post(
        "/chat/rooms", json={"group_id": group_id, "name": "관리자가 만든 방"}, headers=auth
    ).json()

    member = _signup(client, "member@onque.dev", "직원")
    client.post(
        f"/api/v1/groups/{group_id}/members", json={"user_id": member["user"]["id"]}, headers=auth
    )
    # 방에 초대까지 해야 "방 멤버지만 방장은 아닌 사람"의 삭제 시도를 검증할 수 있다.
    client.post(
        f"/chat/rooms/{room['id']}/members", json={"user_id": member["user"]["id"]}, headers=auth
    )

    res = client.delete(
        f"/chat/rooms/{room['id']}", headers={"Authorization": f"Bearer {member['token']}"}
    )

    assert res.status_code == 403
    assert res.json()["error"]["code"] == "CHAT_ROOM_DELETE_FORBIDDEN"


def test_group_admin_can_delete_someone_elses_room(client):
    owner_data = _signup(client, "r1@t.dev", "관리자")
    owner_headers = {"Authorization": f"Bearer {owner_data['token']}"}
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner_headers).json()["data"]["id"]
    client.post(f"/api/v1/groups/{gid}/invitations", json={"email": "r2@t.dev"}, headers=owner_headers)
    member_data = _signup(client, "r2@t.dev", "멤버")
    member_headers = {"Authorization": f"Bearer {member_data['token']}"}

    room_id = client.post(
        "/chat/rooms", json={"group_id": gid, "name": "멤버방"}, headers=member_headers
    ).json()["id"]

    assert client.delete(f"/chat/rooms/{room_id}", headers=owner_headers).status_code == 200


def test_group_admin_can_kick_someone_elses_room_member(client, db_session):
    """방 멤버가 아닌 그룹 admin도 다른 사람이 만든 방의 멤버를 강퇴할 수 있어야 한다."""
    owner_data = _signup(client, "r6@t.dev", "관리자")
    owner_headers = {"Authorization": f"Bearer {owner_data['token']}"}
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner_headers).json()["data"]["id"]
    for email in ("r7@t.dev", "r8@t.dev"):
        client.post(f"/api/v1/groups/{gid}/invitations", json={"email": email}, headers=owner_headers)
    creator_data = _signup(client, "r7@t.dev", "방장")
    creator_headers = {"Authorization": f"Bearer {creator_data['token']}"}
    target_data = _signup(client, "r8@t.dev", "멤버")
    target_headers = {"Authorization": f"Bearer {target_data['token']}"}
    target_id = _user_id(client, target_headers)

    room_id = client.post(
        "/chat/rooms", json={"group_id": gid, "name": "다른방"}, headers=creator_headers
    ).json()["id"]
    client.post(
        f"/chat/rooms/{room_id}/members", json={"user_id": target_id}, headers=creator_headers
    )

    res = client.delete(f"/chat/rooms/{room_id}/members/{target_id}", headers=owner_headers)
    assert res.status_code == 200

    remaining = db_session.get(ChatRoomMember, {"room_id": room_id, "user_id": target_id})
    assert remaining is None


def test_plain_member_cannot_delete_someone_elses_room(client):
    owner_data = _signup(client, "r3@t.dev", "관리자")
    owner_headers = {"Authorization": f"Bearer {owner_data['token']}"}
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner_headers).json()["data"]["id"]
    for email in ("r4@t.dev", "r5@t.dev"):
        client.post(f"/api/v1/groups/{gid}/invitations", json={"email": email}, headers=owner_headers)
    a_data = _signup(client, "r4@t.dev", "A")
    a_headers = {"Authorization": f"Bearer {a_data['token']}"}
    b_data = _signup(client, "r5@t.dev", "B")
    b_headers = {"Authorization": f"Bearer {b_data['token']}"}

    room_id = client.post(
        "/chat/rooms", json={"group_id": gid, "name": "A방"}, headers=a_headers
    ).json()["id"]
    client.post(
        f"/chat/rooms/{room_id}/members", json={"user_id": _user_id(client, b_headers)}, headers=a_headers
    )

    res = client.delete(f"/chat/rooms/{room_id}", headers=b_headers)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "CHAT_ROOM_DELETE_FORBIDDEN"
