from datetime import date

from models import Document, Schedule, Todo


def _signup(client, email, name):
    res = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "password123", "name": name},
    )
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['data']['token']}"}


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
        f"/api/v1/groups/{group_a}/invitations",
        json={"email": "a-member@onque.dev"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    inv_id = client.get(
        "/api/v1/me/invitations", headers={"Authorization": f"Bearer {member_token}"}
    ).json()["data"][0]["id"]
    client.post(
        f"/api/v1/me/invitations/{inv_id}/accept",
        headers={"Authorization": f"Bearer {member_token}"},
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


def test_chat_messages_isolated_between_rooms(client):
    admin_token, group_a, group_b = _setup_two_groups(client)
    auth = {"Authorization": f"Bearer {admin_token}"}

    # 그룹 생성 시 기본 방이 함께 만들어진다.
    room_a = client.get("/chat/rooms", params={"group_id": group_a}, headers=auth).json()[0]
    room_b = client.get("/chat/rooms", params={"group_id": group_b}, headers=auth).json()[0]

    client.post(
        "/chat/messages",
        params={"room_id": room_a["id"]},
        json={"sender": "관리자", "content": "안녕하세요"},
        headers=auth,
    )

    res_a = client.get("/chat/messages", params={"room_id": room_a["id"]}, headers=auth)
    res_b = client.get("/chat/messages", params={"room_id": room_b["id"]}, headers=auth)
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


def test_schedule_requires_a_group(client):
    """전사 일정 개념을 없앴다. group_id 없이 만들 수 없다."""
    headers = _signup(client, "sch@t.dev", "일정")
    res = client.post(
        "/schedules", json={"title": "회의", "scheduled_date": "2026-09-01"}, headers=headers
    )
    assert res.status_code == 422


def test_group_member_can_delete_group_document(client, db_session):
    """현재 동작 유지 — 작성자 컬럼이 없어 '본인 것만'을 구현할 수 없다."""
    owner = _signup(client, "d1@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    client.post(f"/api/v1/groups/{gid}/invitations", json={"email": "d2@t.dev"}, headers=owner)
    member = _signup(client, "d2@t.dev", "멤버")
    # 초대만으로는 합류하지 않는다. 수락해야 멤버가 된다.
    inv_id = client.get("/api/v1/me/invitations", headers=member).json()["data"][0]["id"]
    client.post(f"/api/v1/me/invitations/{inv_id}/accept", headers=member)

    doc = Document(
        group_id=gid, source_type="document", category="기타",
        filename="a.txt", summary="요약",
    )
    db_session.add(doc)
    db_session.commit()

    assert client.delete(f"/documents/{doc.id}", headers=member).status_code == 200


def test_groupless_document_cannot_be_deleted_by_anyone(client, db_session):
    """전역 admin이 사라져 이 문서를 지울 주체가 없다. 운영에 0건이지만 방어한다."""
    headers = _signup(client, "d3@t.dev", "누구")
    doc = Document(
        group_id=None, source_type="document", category="기타",
        filename="orphan.txt", summary="요약",
    )
    db_session.add(doc)
    db_session.commit()

    res = client.delete(f"/documents/{doc.id}", headers=headers)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "DOCUMENT_DELETE_FORBIDDEN"


def test_groupless_schedule_cannot_be_updated_by_anyone(client, db_session):
    """전역 admin이 사라져 이 일정을 수정할 주체가 없다. 운영에 0건이지만 방어한다."""
    headers = _signup(client, "s1@t.dev", "누구")
    schedule = Schedule(group_id=None, title="고아 일정", scheduled_date=date(2026, 9, 1))
    db_session.add(schedule)
    db_session.commit()

    res = client.patch(
        f"/schedules/{schedule.id}", json={"title": "바꾼 제목"}, headers=headers
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "SCHEDULE_EDIT_FORBIDDEN"


def test_groupless_schedule_cannot_be_deleted_by_anyone(client, db_session):
    """전역 admin이 사라져 이 일정을 지울 주체가 없다. 운영에 0건이지만 방어한다."""
    headers = _signup(client, "s2@t.dev", "누구")
    schedule = Schedule(group_id=None, title="고아 일정", scheduled_date=date(2026, 9, 1))
    db_session.add(schedule)
    db_session.commit()

    res = client.delete(f"/schedules/{schedule.id}", headers=headers)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "SCHEDULE_EDIT_FORBIDDEN"
