def _signup(client, email, name):
    return client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "password123", "name": name},
    ).json()["data"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _invite_and_accept(client, admin_auth, group_id, email, member_auth):
    client.post(
        f"/api/v1/groups/{group_id}/invitations", json={"email": email}, headers=admin_auth
    )
    inv_id = client.get("/api/v1/me/invitations", headers=member_auth).json()["data"][0]["id"]
    client.post(f"/api/v1/me/invitations/{inv_id}/accept", headers=member_auth)


def _setup(client):
    """관리자 + 같은 그룹의 일반 멤버 한 명."""
    admin = _signup(client, "admin@onque.dev", "관리자")
    admin_auth = _auth(admin["token"])
    group_id = client.post(
        "/api/v1/groups", json={"name": "A팀"}, headers=admin_auth
    ).json()["data"]["id"]

    member = _signup(client, "member@onque.dev", "직원")
    _invite_and_accept(
        client, admin_auth, group_id, "member@onque.dev", _auth(member["token"])
    )
    return admin, member, group_id


def _make_room(client, token, group_id, name):
    return client.post(
        "/chat/rooms", json={"group_id": group_id, "name": name}, headers=_auth(token)
    ).json()


def test_creator_is_the_only_member_of_a_new_room(client):
    admin, _, group_id = _setup(client)
    room = _make_room(client, admin["token"], group_id, "디자인 리뷰")

    members = client.get(
        f"/chat/rooms/{room['id']}/members", headers=_auth(admin["token"])
    ).json()

    assert [m["name"] for m in members] == ["관리자"]
    assert members[0]["is_owner"] is True
    assert room["member_count"] == 1


def test_group_member_cannot_see_or_enter_a_room_they_were_not_invited_to(client):
    admin, member, group_id = _setup(client)
    room = _make_room(client, admin["token"], group_id, "임원 회의")

    rooms = client.get(
        "/chat/rooms", params={"group_id": group_id}, headers=_auth(member["token"])
    ).json()
    assert room["id"] not in [r["id"] for r in rooms]

    res = client.get(
        "/chat/messages", params={"room_id": room["id"]}, headers=_auth(member["token"])
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "CHAT_ROOM_FORBIDDEN"


def test_invited_member_sees_the_room_and_can_read_messages(client):
    admin, member, group_id = _setup(client)
    room = _make_room(client, admin["token"], group_id, "디자인 리뷰")
    client.post(
        "/chat/messages",
        params={"room_id": room["id"]},
        json={"sender": "관리자", "content": "시안 공유합니다"},
        headers=_auth(admin["token"]),
    )

    invited = client.post(
        f"/chat/rooms/{room['id']}/members",
        json={"user_id": member["user"]["id"]},
        headers=_auth(admin["token"]),
    )
    assert invited.status_code == 200
    assert invited.json()["is_owner"] is False

    rooms = client.get(
        "/chat/rooms", params={"group_id": group_id}, headers=_auth(member["token"])
    ).json()
    target = next(r for r in rooms if r["id"] == room["id"])
    assert target["member_count"] == 2

    messages = client.get(
        "/chat/messages", params={"room_id": room["id"]}, headers=_auth(member["token"])
    ).json()
    assert [m["content"] for m in messages] == ["시안 공유합니다"]


def test_invited_member_can_invite_someone_else(client):
    admin, member, group_id = _setup(client)
    room = _make_room(client, admin["token"], group_id, "디자인 리뷰")
    client.post(
        f"/chat/rooms/{room['id']}/members",
        json={"user_id": member["user"]["id"]},
        headers=_auth(admin["token"]),
    )

    third = _signup(client, "third@onque.dev", "신입")
    _invite_and_accept(
        client, _auth(admin["token"]), group_id, "third@onque.dev", _auth(third["token"])
    )

    res = client.post(
        f"/chat/rooms/{room['id']}/members",
        json={"user_id": third["user"]["id"]},
        headers=_auth(member["token"]),
    )

    assert res.status_code == 200


def test_cannot_invite_someone_outside_the_group(client):
    admin, _, group_id = _setup(client)
    room = _make_room(client, admin["token"], group_id, "디자인 리뷰")
    outsider = _signup(client, "outsider@onque.dev", "외부인")

    res = client.post(
        f"/chat/rooms/{room['id']}/members",
        json={"user_id": outsider["user"]["id"]},
        headers=_auth(admin["token"]),
    )

    assert res.status_code == 403
    assert res.json()["error"]["code"] == "CHAT_ROOM_INVITE_NOT_IN_GROUP"


def test_inviting_twice_is_rejected(client):
    admin, member, group_id = _setup(client)
    room = _make_room(client, admin["token"], group_id, "디자인 리뷰")
    body = {"user_id": member["user"]["id"]}
    client.post(f"/chat/rooms/{room['id']}/members", json=body, headers=_auth(admin["token"]))

    res = client.post(
        f"/chat/rooms/{room['id']}/members", json=body, headers=_auth(admin["token"])
    )

    assert res.status_code == 409
    assert res.json()["error"]["code"] == "CHAT_ROOM_MEMBER_EXISTS"


def test_member_can_leave_but_cannot_kick_others(client):
    admin, member, group_id = _setup(client)
    room = _make_room(client, admin["token"], group_id, "디자인 리뷰")
    client.post(
        f"/chat/rooms/{room['id']}/members",
        json={"user_id": member["user"]["id"]},
        headers=_auth(admin["token"]),
    )

    kick = client.delete(
        f"/chat/rooms/{room['id']}/members/{admin['user']['id']}",
        headers=_auth(member["token"]),
    )
    assert kick.status_code == 403
    assert kick.json()["error"]["code"] == "CHAT_ROOM_MEMBER_REMOVE_FORBIDDEN"

    leave = client.delete(
        f"/chat/rooms/{room['id']}/members/{member['user']['id']}",
        headers=_auth(member["token"]),
    )
    assert leave.status_code == 200
    assert leave.json()["room_deleted"] is False

    rooms = client.get(
        "/chat/rooms", params={"group_id": group_id}, headers=_auth(member["token"])
    ).json()
    assert room["id"] not in [r["id"] for r in rooms]


def test_room_owner_can_kick_a_member(client):
    admin, member, group_id = _setup(client)
    room = _make_room(client, admin["token"], group_id, "디자인 리뷰")
    client.post(
        f"/chat/rooms/{room['id']}/members",
        json={"user_id": member["user"]["id"]},
        headers=_auth(admin["token"]),
    )

    res = client.delete(
        f"/chat/rooms/{room['id']}/members/{member['user']['id']}",
        headers=_auth(admin["token"]),
    )

    assert res.status_code == 200
    members = client.get(
        f"/chat/rooms/{room['id']}/members", headers=_auth(admin["token"])
    ).json()
    assert [m["name"] for m in members] == ["관리자"]


def test_last_member_leaving_deletes_the_room(client):
    admin, _, group_id = _setup(client)
    room = _make_room(client, admin["token"], group_id, "혼자 쓰던 방")
    client.post(
        "/chat/messages",
        params={"room_id": room["id"]},
        json={"sender": "관리자", "content": "메모"},
        headers=_auth(admin["token"]),
    )

    res = client.delete(
        f"/chat/rooms/{room['id']}/members/{admin['user']['id']}",
        headers=_auth(admin["token"]),
    )

    assert res.json()["room_deleted"] is True
    check = client.get(
        "/chat/messages", params={"room_id": room["id"]}, headers=_auth(admin["token"])
    )
    assert check.status_code == 404


def test_new_group_member_joins_the_default_room_only(client):
    admin, member, group_id = _setup(client)
    _make_room(client, admin["token"], group_id, "주제별 방")

    rooms = client.get(
        "/chat/rooms", params={"group_id": group_id}, headers=_auth(member["token"])
    ).json()

    assert [r["name"] for r in rooms] == ["일반"]


def test_removing_a_group_member_clears_their_room_memberships(client):
    admin, member, group_id = _setup(client)
    admin_auth = _auth(admin["token"])
    room = _make_room(client, admin["token"], group_id, "디자인 리뷰")
    client.post(
        f"/chat/rooms/{room['id']}/members",
        json={"user_id": member["user"]["id"]},
        headers=admin_auth,
    )

    client.delete(
        f"/api/v1/groups/{group_id}/members/{member['user']['id']}", headers=admin_auth
    )

    members = client.get(f"/chat/rooms/{room['id']}/members", headers=admin_auth).json()
    assert [m["name"] for m in members] == ["관리자"]
