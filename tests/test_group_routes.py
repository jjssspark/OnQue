def _signup(client, email, name="테스트"):
    res = client.post(
        "/api/v1/auth/signup", json={"email": email, "password": "password123", "name": name}
    )
    body = res.json()["data"]
    return body["token"], body["user"]["id"]


def _signup_headers(client, email, name):
    res = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "password123", "name": name},
    )
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['data']['token']}"}


def test_any_user_can_create_a_group_and_becomes_its_admin(client):
    _signup_headers(client, "first@t.dev", "첫째")          # 예전이라면 이 사람만 admin
    headers = _signup_headers(client, "second@t.dev", "둘째")

    res = client.post("/api/v1/groups", json={"name": "둘째팀"}, headers=headers)
    assert res.status_code == 200
    group_id = res.json()["data"]["id"]

    me = client.get("/api/v1/me", headers=headers).json()["data"]
    assert [g["role"] for g in me["groups"] if g["id"] == group_id] == ["admin"]


def test_group_creation_is_atomic(client, db_session):
    """그룹만 남고 멤버십이 없으면 만든 사람도 자기 그룹에 못 들어간다."""
    from models import ChatRoomMember, Group, GroupMembership

    headers = _signup_headers(client, "solo@t.dev", "혼자")
    group_id = client.post(
        "/api/v1/groups", json={"name": "혼자팀"}, headers=headers
    ).json()["data"]["id"]

    assert db_session.get(Group, group_id) is not None
    memberships = db_session.query(GroupMembership).filter_by(group_id=group_id).all()
    assert len(memberships) == 1 and memberships[0].role == "admin"
    # 기본 방에도 들어가 있어야 채팅 화면이 빈 목록이 아니다
    assert db_session.query(ChatRoomMember).count() == 1


def test_new_user_starts_with_no_groups(client):
    """가입 직후 소속 그룹이 없어야 프론트가 팀 만들기 폼을 띄운다."""
    headers = _signup_headers(client, "fresh@t.dev", "신규")
    assert client.get("/api/v1/me", headers=headers).json()["data"]["groups"] == []


def test_invited_member_joins_as_member_not_admin(client):
    admin_headers = _signup_headers(client, "owner@t.dev", "주인")
    group_id = client.post(
        "/api/v1/groups", json={"name": "A팀"}, headers=admin_headers
    ).json()["data"]["id"]

    client.post(
        f"/api/v1/groups/{group_id}/invitations",
        json={"email": "guest@t.dev"},
        headers=admin_headers,
    )
    guest_headers = _signup_headers(client, "guest@t.dev", "손님")

    me = client.get("/api/v1/me", headers=guest_headers).json()["data"]
    assert [g["role"] for g in me["groups"]] == ["member"]


def test_admin_can_create_group(client):
    admin_token, _ = _signup(client, "admin@onque.dev")
    res = client.post(
        "/api/v1/groups",
        json={"name": "행사기획팀"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["name"] == "행사기획팀"


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
