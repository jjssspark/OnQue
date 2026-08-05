from models import Document, Todo


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


def test_todos_isolated_between_groups(client, db_session):
    admin_token, group_a, group_b = _setup_two_groups(client)
    # Seed a todo directly — chat-based extraction depends on gemini_service,
    # which is not exercised in the test environment (GOOGLE_API_KEY="test-key").
    db_session.add(Todo(group_id=group_a, content="A팀 킥오프 준비"))
    db_session.commit()

    res_a = client.get(
        "/todos", params={"group_id": group_a}, headers={"Authorization": f"Bearer {admin_token}"}
    )
    res_b = client.get(
        "/todos", params={"group_id": group_b}, headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert [t["content"] for t in res_a.json()] == ["A팀 킥오프 준비"]
    assert res_b.json() == []


def test_todo_patch_rejects_cross_group_access(client, db_session):
    admin_token, group_a, group_b = _setup_two_groups(client)
    todo = Todo(group_id=group_b, content="B팀 전용 할 일")
    db_session.add(todo)
    db_session.commit()
    db_session.refresh(todo)

    member_signup = client.post(
        "/api/v1/auth/signup",
        json={"email": "a-member@onque.dev", "password": "password123", "name": "A팀원"},
    ).json()["data"]
    member_token = member_signup["token"]
    client.post(
        f"/api/v1/groups/{group_a}/members",
        json={"user_id": member_signup["user"]["id"]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    res = client.patch(
        f"/todos/{todo.id}",
        json={"is_done": True},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "GROUP_ACCESS_FORBIDDEN"


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


def test_documents_isolated_between_groups(client, db_session):
    admin_token, group_a, group_b = _setup_two_groups(client)
    # 문서는 gemini 요약 엔드포인트로만 생성되므로 직접 seed한다.
    db_session.add(
        Document(
            group_id=group_a,
            source_type="document",
            category="기획",
            filename="a-team-plan.pdf",
            summary="A팀 기획안 요약",
        )
    )
    db_session.commit()

    res_a = client.get(
        "/documents", params={"group_id": group_a}, headers={"Authorization": f"Bearer {admin_token}"}
    )
    res_b = client.get(
        "/documents", params={"group_id": group_b}, headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert [d["filename"] for d in res_a.json()] == ["a-team-plan.pdf"]
    assert res_b.json() == []


def test_template_document_visible_in_every_group(client, db_session):
    admin_token, group_a, group_b = _setup_two_groups(client)
    db_session.add(
        Document(
            group_id=None,
            is_template=True,
            source_type="document",
            category="기타",
            filename="company-template.docx",
            summary="전사 공용 템플릿",
        )
    )
    db_session.commit()

    res_a = client.get(
        "/documents", params={"group_id": group_a}, headers={"Authorization": f"Bearer {admin_token}"}
    )
    res_b = client.get(
        "/documents", params={"group_id": group_b}, headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert "company-template.docx" in [d["filename"] for d in res_a.json()]
    assert "company-template.docx" in [d["filename"] for d in res_b.json()]


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
