def _signup(client, email, name="테스트"):
    res = client.post(
        "/api/v1/auth/signup", json={"email": email, "password": "password123", "name": name}
    )
    body = res.json()["data"]
    return body["token"], body["user"]["id"]


def test_admin_can_create_group(client):
    admin_token, _ = _signup(client, "admin@onque.dev")
    res = client.post(
        "/api/v1/groups",
        json={"name": "행사기획팀"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["name"] == "행사기획팀"


def test_member_cannot_create_group(client):
    _signup(client, "admin@onque.dev")
    member_token, _ = _signup(client, "member@onque.dev")
    res = client.post(
        "/api/v1/groups",
        json={"name": "행사기획팀"},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "GROUP_CREATE_FORBIDDEN"


def test_admin_can_add_member_to_group(client):
    admin_token, _ = _signup(client, "admin@onque.dev")
    _, member_id = _signup(client, "member@onque.dev")
    group = client.post(
        "/api/v1/groups",
        json={"name": "행사기획팀"},
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()["data"]

    res = client.post(
        f"/api/v1/groups/{group['id']}/members",
        json={"user_id": member_id},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200

    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {admin_token}"})


def test_member_cannot_add_member(client):
    admin_token, _ = _signup(client, "admin@onque.dev")
    _, member_id = _signup(client, "member@onque.dev")
    other_token, other_id = _signup(client, "other@onque.dev")
    group = client.post(
        "/api/v1/groups",
        json={"name": "행사기획팀"},
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()["data"]

    res = client.post(
        f"/api/v1/groups/{group['id']}/members",
        json={"user_id": other_id},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "GROUP_MEMBER_ADD_FORBIDDEN"


def test_get_groups_returns_only_my_groups(client):
    admin_token, admin_id = _signup(client, "admin@onque.dev")
    _, member_id = _signup(client, "member@onque.dev")
    group_a = client.post(
        "/api/v1/groups", json={"name": "A팀"}, headers={"Authorization": f"Bearer {admin_token}"}
    ).json()["data"]
    client.post(
        "/api/v1/groups", json={"name": "B팀"}, headers={"Authorization": f"Bearer {admin_token}"}
    )
    client.post(
        f"/api/v1/groups/{group_a['id']}/members",
        json={"user_id": member_id},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    member_token = client.post(
        "/api/v1/auth/login", json={"email": "member@onque.dev", "password": "password123"}
    ).json()["data"]["token"]
    res = client.get("/api/v1/groups", headers={"Authorization": f"Bearer {member_token}"})
    names = [g["name"] for g in res.json()["data"]]
    assert names == ["A팀"]


def test_admin_can_remove_member_from_group(client):
    admin_token, _ = _signup(client, "admin@onque.dev")
    _, member_id = _signup(client, "member@onque.dev")
    group = client.post(
        "/api/v1/groups",
        json={"name": "행사기획팀"},
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()["data"]
    client.post(
        f"/api/v1/groups/{group['id']}/members",
        json={"user_id": member_id},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    res = client.delete(
        f"/api/v1/groups/{group['id']}/members/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200

    member_token = client.post(
        "/api/v1/auth/login", json={"email": "member@onque.dev", "password": "password123"}
    ).json()["data"]["token"]
    res = client.get("/api/v1/groups", headers={"Authorization": f"Bearer {member_token}"})
    names = [g["name"] for g in res.json()["data"]]
    assert names == []


def test_member_cannot_remove_member(client):
    admin_token, _ = _signup(client, "admin@onque.dev")
    _, member_id = _signup(client, "member@onque.dev")
    other_token, _ = _signup(client, "other@onque.dev")
    group = client.post(
        "/api/v1/groups",
        json={"name": "행사기획팀"},
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()["data"]
    client.post(
        f"/api/v1/groups/{group['id']}/members",
        json={"user_id": member_id},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    res = client.delete(
        f"/api/v1/groups/{group['id']}/members/{member_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "GROUP_MEMBER_ADD_FORBIDDEN"
