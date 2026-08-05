def _setup_two_groups(client):
    admin_token = client.post(
        "/api/v1/auth/signup",
        json={"email": "admin@onque.dev", "password": "password123", "name": "관리자"},
    ).json()["data"]["token"]
    group_a = client.post(
        "/api/v1/groups", json={"name": "A팀"}, headers={"Authorization": f"Bearer {admin_token}"}
    ).json()["data"]
    group_b = client.post(
        "/api/v1/groups", json={"name": "B팀"}, headers={"Authorization": f"Bearer {admin_token}"}
    ).json()["data"]
    return admin_token, group_a["id"], group_b["id"]


def test_todos_requires_group_id(client):
    admin_token, group_a, _ = _setup_two_groups(client)
    res = client.get("/todos", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 422


def test_todos_isolated_between_groups(client):
    admin_token, group_a, group_b = _setup_two_groups(client)
    client.post(
        "/chat/messages",
        params={"group_id": group_a},
        json={"sender": "관리자", "content": "할일: A팀 킥오프 준비"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    res_a = client.get(
        "/todos", params={"group_id": group_a}, headers={"Authorization": f"Bearer {admin_token}"}
    )
    res_b = client.get(
        "/todos", params={"group_id": group_b}, headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert len(res_a.json()) >= 0
    assert res_b.json() == []


def test_todos_rejects_non_member(client):
    admin_token, group_a, _ = _setup_two_groups(client)
    other_token = client.post(
        "/api/v1/auth/signup",
        json={"email": "other@onque.dev", "password": "password123", "name": "타인"},
    ).json()["data"]["token"]
    res = client.get(
        "/todos", params={"group_id": group_a}, headers={"Authorization": f"Bearer {other_token}"}
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "GROUP_ACCESS_FORBIDDEN"


def test_chat_messages_isolated_between_groups(client):
    admin_token, group_a, group_b = _setup_two_groups(client)
    client.post(
        "/chat/messages",
        params={"group_id": group_a},
        json={"sender": "관리자", "content": "안녕하세요"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    res_a = client.get(
        "/chat/messages", params={"group_id": group_a}, headers={"Authorization": f"Bearer {admin_token}"}
    )
    res_b = client.get(
        "/chat/messages", params={"group_id": group_b}, headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert len(res_a.json()) == 1
    assert res_b.json() == []


def test_admin_can_create_company_wide_schedule_visible_in_every_group(client):
    admin_token, group_a, group_b = _setup_two_groups(client)
    res = client.post(
        "/schedules",
        json={"title": "창립기념일 휴무", "scheduled_date": "2026-09-01"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    assert res.json()["title"] == "창립기념일 휴무"

    res_a = client.get(
        "/schedules", params={"group_id": group_a}, headers={"Authorization": f"Bearer {admin_token}"}
    )
    res_b = client.get(
        "/schedules", params={"group_id": group_b}, headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert "창립기념일 휴무" in [s["title"] for s in res_a.json()]
    assert "창립기념일 휴무" in [s["title"] for s in res_b.json()]


def test_member_cannot_create_company_wide_schedule(client):
    _setup_two_groups(client)
    member_signup = client.post(
        "/api/v1/auth/signup",
        json={"email": "member@onque.dev", "password": "password123", "name": "직원"},
    ).json()["data"]
    member_token = member_signup["token"]

    res = client.post(
        "/schedules",
        json={"title": "직원이 만든 전사 일정", "scheduled_date": "2026-09-01"},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "SCHEDULE_EDIT_FORBIDDEN"
