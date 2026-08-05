def _signup(client, email: str, name: str) -> str:
    res = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "password123", "name": name},
    )
    return res.json()["data"]["token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_admin_can_list_users(client):
    admin_token = _signup(client, "admin@onque.dev", "관리자")
    _signup(client, "member@onque.dev", "직원")

    res = client.get("/api/v1/users", headers=_auth(admin_token))
    assert res.status_code == 200
    emails = [u["email"] for u in res.json()["data"]]
    assert emails == ["admin@onque.dev", "member@onque.dev"]


def test_member_cannot_list_users(client):
    _signup(client, "admin@onque.dev", "관리자")
    member_token = _signup(client, "member@onque.dev", "직원")

    res = client.get("/api/v1/users", headers=_auth(member_token))
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "USER_LIST_FORBIDDEN"


def test_group_members_lists_only_that_group(client):
    admin_token = _signup(client, "admin@onque.dev", "관리자")
    member_token = _signup(client, "member@onque.dev", "직원")
    member_id = client.get("/api/v1/me", headers=_auth(member_token)).json()["data"]["user"]["id"]

    group_id = client.post(
        "/api/v1/groups", json={"name": "디자인팀"}, headers=_auth(admin_token)
    ).json()["data"]["id"]
    client.post(
        f"/api/v1/groups/{group_id}/members",
        json={"user_id": member_id},
        headers=_auth(admin_token),
    )

    res = client.get(f"/api/v1/groups/{group_id}/members", headers=_auth(admin_token))
    assert res.status_code == 200
    assert sorted(u["email"] for u in res.json()["data"]) == [
        "admin@onque.dev",
        "member@onque.dev",
    ]


def test_member_cannot_list_members_of_foreign_group(client):
    admin_token = _signup(client, "admin@onque.dev", "관리자")
    outsider_token = _signup(client, "outsider@onque.dev", "외부인")

    group_id = client.post(
        "/api/v1/groups", json={"name": "비밀팀"}, headers=_auth(admin_token)
    ).json()["data"]["id"]

    res = client.get(
        f"/api/v1/groups/{group_id}/members", headers=_auth(outsider_token)
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "GROUP_ACCESS_FORBIDDEN"


def test_group_members_returns_404_for_missing_group(client):
    admin_token = _signup(client, "admin@onque.dev", "관리자")
    res = client.get("/api/v1/groups/9999/members", headers=_auth(admin_token))
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "GROUP_NOT_FOUND"
