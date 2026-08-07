def _signup(client, email, name):
    res = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "password123", "name": name},
    )
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['data']['token']}"}


def test_admin_can_post_announcement(client):
    admin = _signup(client, "admin@onque.dev", "관리자")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=admin).json()["data"]["id"]
    res = client.post(
        "/api/v1/announcements",
        json={"group_id": gid, "title": "팀 공지", "content": "내용"},
        headers=admin,
    )
    assert res.status_code == 200
    assert res.json()["data"]["title"] == "팀 공지"


def test_announcement_is_scoped_to_its_group(client):
    a = _signup(client, "ga@t.dev", "A관리자")
    b = _signup(client, "gb@t.dev", "B관리자")
    gid_a = client.post("/api/v1/groups", json={"name": "A팀"}, headers=a).json()["data"]["id"]
    gid_b = client.post("/api/v1/groups", json={"name": "B팀"}, headers=b).json()["data"]["id"]

    client.post(
        "/api/v1/announcements",
        json={"group_id": gid_a, "title": "A팀 공지", "content": "내용"},
        headers=a,
    )

    assert len(client.get(f"/api/v1/announcements?group_id={gid_a}", headers=a).json()["data"]) == 1
    assert client.get(f"/api/v1/announcements?group_id={gid_b}", headers=b).json()["data"] == []
    # 남의 팀 공지는 조회 자체가 막힌다
    assert client.get(f"/api/v1/announcements?group_id={gid_a}", headers=b).status_code == 403


def test_member_cannot_write_announcement(client):
    owner = _signup(client, "gc@t.dev", "관리자")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    client.post(f"/api/v1/groups/{gid}/invitations", json={"email": "gd@t.dev"}, headers=owner)
    member = _signup(client, "gd@t.dev", "멤버")

    # Owner가 공지를 쓴다
    client.post(
        "/api/v1/announcements",
        json={"group_id": gid, "title": "공지", "content": "내용"},
        headers=owner,
    )

    # Member는 작성할 수 없다
    res = client.post(
        "/api/v1/announcements",
        json={"group_id": gid, "title": "몰래", "content": "내용"},
        headers=member,
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "ANNOUNCEMENT_CREATE_FORBIDDEN"

    # 하지만 목록은 볼 수 있다
    list_res = client.get(f"/api/v1/announcements?group_id={gid}", headers=member)
    assert list_res.status_code == 200
    assert len(list_res.json()["data"]) == 1
    assert list_res.json()["data"][0]["title"] == "공지"


def test_announcement_list_is_paginated(client):
    owner = _signup(client, "ge@t.dev", "관리자")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    for i in range(25):
        client.post(
            "/api/v1/announcements",
            json={"group_id": gid, "title": f"공지{i}", "content": "내용"},
            headers=owner,
        )

    body = client.get(f"/api/v1/announcements?group_id={gid}", headers=owner).json()
    assert len(body["data"]) == 20
    assert body["meta"] == {"total": 25, "limit": 20, "hasNext": True}
