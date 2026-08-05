def _signup(client, email, name):
    return client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "password123", "name": name},
    ).json()["data"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _setup(client):
    admin = _signup(client, "admin@onque.dev", "관리자")
    group_id = client.post(
        "/api/v1/groups", json={"name": "A팀"}, headers=_auth(admin["token"])
    ).json()["data"]["id"]
    return admin, group_id


def _invite(client, token, group_id, email):
    return client.post(
        f"/api/v1/groups/{group_id}/invitations",
        json={"email": email},
        headers=_auth(token),
    )


def test_inviting_an_unregistered_email_stays_pending(client):
    admin, group_id = _setup(client)

    res = _invite(client, admin["token"], group_id, "newbie@onque.dev")

    assert res.status_code == 200
    assert res.json()["data"]["status"] == "pending"

    pending = client.get(
        f"/api/v1/groups/{group_id}/invitations", headers=_auth(admin["token"])
    ).json()["data"]
    assert [i["email"] for i in pending] == ["newbie@onque.dev"]
    assert pending[0]["accepted_at"] is None


def test_signing_up_with_an_invited_email_joins_the_group(client):
    admin, group_id = _setup(client)
    _invite(client, admin["token"], group_id, "newbie@onque.dev")

    newbie = _signup(client, "newbie@onque.dev", "신입")

    groups = client.get("/api/v1/me", headers=_auth(newbie["token"])).json()["data"]["groups"]
    assert [g["id"] for g in groups] == [group_id]

    # 대기 목록에서는 빠지고, 기본 방에는 들어가 있어야 한다.
    pending = client.get(
        f"/api/v1/groups/{group_id}/invitations", headers=_auth(admin["token"])
    ).json()["data"]
    assert pending == []

    rooms = client.get(
        "/chat/rooms", params={"group_id": group_id}, headers=_auth(newbie["token"])
    ).json()
    assert [r["name"] for r in rooms] == ["일반"]


def test_email_case_does_not_split_the_invitation(client):
    admin, group_id = _setup(client)
    _invite(client, admin["token"], group_id, "NewBie@OnQue.dev")

    newbie = _signup(client, "newbie@onque.dev", "신입")

    groups = client.get("/api/v1/me", headers=_auth(newbie["token"])).json()["data"]["groups"]
    assert [g["id"] for g in groups] == [group_id]


def test_inviting_an_existing_user_joins_them_immediately(client):
    admin, group_id = _setup(client)
    existing = _signup(client, "member@onque.dev", "직원")

    res = _invite(client, admin["token"], group_id, "member@onque.dev")

    assert res.status_code == 200
    assert res.json()["data"]["status"] == "joined"

    groups = client.get("/api/v1/me", headers=_auth(existing["token"])).json()["data"]["groups"]
    assert group_id in [g["id"] for g in groups]
    # 바로 합류했으니 대기 목록에는 남지 않는다.
    pending = client.get(
        f"/api/v1/groups/{group_id}/invitations", headers=_auth(admin["token"])
    ).json()["data"]
    assert pending == []


def test_inviting_the_same_email_twice_is_rejected(client):
    admin, group_id = _setup(client)
    _invite(client, admin["token"], group_id, "newbie@onque.dev")

    res = _invite(client, admin["token"], group_id, "newbie@onque.dev")

    assert res.status_code == 409
    assert res.json()["error"]["code"] == "GROUP_INVITE_ALREADY_SENT"


def test_inviting_an_existing_group_member_is_rejected(client):
    admin, group_id = _setup(client)

    res = _invite(client, admin["token"], group_id, "admin@onque.dev")

    assert res.status_code == 409
    assert res.json()["error"]["code"] == "GROUP_INVITE_ALREADY_MEMBER"


def test_non_admin_cannot_invite(client):
    admin, group_id = _setup(client)
    member = _signup(client, "member@onque.dev", "직원")
    client.post(
        f"/api/v1/groups/{group_id}/members",
        json={"user_id": member["user"]["id"]},
        headers=_auth(admin["token"]),
    )

    res = _invite(client, member["token"], group_id, "newbie@onque.dev")

    assert res.status_code == 403
    assert res.json()["error"]["code"] == "GROUP_INVITE_FORBIDDEN"


def test_malformed_email_is_rejected(client):
    admin, group_id = _setup(client)

    res = _invite(client, admin["token"], group_id, "onque.dev")

    assert res.status_code == 422


def test_cancelled_invitation_does_not_apply_at_signup(client):
    admin, group_id = _setup(client)
    invitation = _invite(client, admin["token"], group_id, "newbie@onque.dev").json()["data"][
        "invitation"
    ]

    cancelled = client.delete(
        f"/api/v1/groups/{group_id}/invitations/{invitation['id']}",
        headers=_auth(admin["token"]),
    )
    assert cancelled.status_code == 200

    newbie = _signup(client, "newbie@onque.dev", "신입")
    groups = client.get("/api/v1/me", headers=_auth(newbie["token"])).json()["data"]["groups"]
    assert groups == []


def test_reinviting_after_a_member_leaves_works(client):
    admin, group_id = _setup(client)
    admin_auth = _auth(admin["token"])
    member = _signup(client, "member@onque.dev", "직원")
    _invite(client, admin["token"], group_id, "member@onque.dev")

    client.delete(
        f"/api/v1/groups/{group_id}/members/{member['user']['id']}", headers=admin_auth
    )

    # 초대 행이 유니크 제약으로 하나뿐이라, 재초대가 막히지 않는지 확인한다.
    res = _invite(client, admin["token"], group_id, "member@onque.dev")
    assert res.status_code == 200
    assert res.json()["data"]["status"] == "joined"


def test_outsider_cannot_read_the_invitation_list(client):
    admin, group_id = _setup(client)
    _invite(client, admin["token"], group_id, "newbie@onque.dev")
    outsider = _signup(client, "outsider@onque.dev", "외부인")

    res = client.get(
        f"/api/v1/groups/{group_id}/invitations", headers=_auth(outsider["token"])
    )

    assert res.status_code == 403
    assert res.json()["error"]["code"] == "GROUP_ACCESS_FORBIDDEN"
