def _signup(client, email):
    res = client.post(
        "/api/v1/auth/signup", json={"email": email, "password": "password123", "name": "테스트"}
    )
    return res.json()["data"]["token"]


def test_admin_can_post_announcement(client):
    token = _signup(client, "admin@onque.dev")
    res = client.post(
        "/api/v1/announcements",
        json={"title": "전사 공지", "content": "내일 휴무입니다."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["title"] == "전사 공지"


def test_member_cannot_post_announcement(client):
    _signup(client, "admin@onque.dev")
    member_token = _signup(client, "member@onque.dev")
    res = client.post(
        "/api/v1/announcements",
        json={"title": "공지", "content": "내용"},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert res.status_code == 403


def test_anyone_can_list_announcements(client):
    admin_token = _signup(client, "admin@onque.dev")
    client.post(
        "/api/v1/announcements",
        json={"title": "공지1", "content": "내용1"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    member_token = _signup(client, "member@onque.dev")
    res = client.get("/api/v1/announcements", headers={"Authorization": f"Bearer {member_token}"})
    assert len(res.json()["data"]) == 1
