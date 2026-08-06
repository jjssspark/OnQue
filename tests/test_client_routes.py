def _setup(client):
    token = client.post(
        "/api/v1/auth/signup",
        json={"email": "admin@onque.dev", "password": "password123", "name": "관리자"},
    ).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    group_a = client.post("/api/v1/groups", json={"name": "A팀"}, headers=headers).json()["data"]
    group_b = client.post("/api/v1/groups", json={"name": "B팀"}, headers=headers).json()["data"]
    return headers, group_a["id"], group_b["id"]


def test_create_and_list_client(client):
    headers, group_a, _ = _setup(client)

    created = client.post(
        "/api/v1/clients", json={"group_id": group_a, "name": "A사"}, headers=headers
    )
    assert created.status_code == 200
    assert created.json()["success"] is True
    assert created.json()["data"]["name"] == "A사"

    listed = client.get("/api/v1/clients", params={"group_id": group_a}, headers=headers)
    assert [c["name"] for c in listed.json()["data"]] == ["A사"]


def test_duplicate_client_name_rejected(client):
    headers, group_a, _ = _setup(client)
    client.post("/api/v1/clients", json={"group_id": group_a, "name": "A사"}, headers=headers)

    dup = client.post(
        "/api/v1/clients", json={"group_id": group_a, "name": "A사"}, headers=headers
    )
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "CLIENT_NAME_DUPLICATE"


def test_clients_isolated_between_groups(client):
    headers, group_a, group_b = _setup(client)
    client.post("/api/v1/clients", json={"group_id": group_a, "name": "A사"}, headers=headers)

    res = client.get("/api/v1/clients", params={"group_id": group_b}, headers=headers)
    assert res.json()["data"] == []


def test_client_requires_group_membership(client):
    headers, group_a, _ = _setup(client)
    other = client.post(
        "/api/v1/auth/signup",
        json={"email": "other@onque.dev", "password": "password123", "name": "외부인"},
    ).json()["data"]["token"]

    res = client.get(
        "/api/v1/clients",
        params={"group_id": group_a},
        headers={"Authorization": f"Bearer {other}"},
    )
    assert res.status_code == 403
