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


def test_accepted_invitation_makes_a_member_not_admin(client):
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
    # 초대만으로는 합류하지 않는다. 수락해야 멤버가 된다.
    inv_id = client.get("/api/v1/me/invitations", headers=guest_headers).json()["data"][0]["id"]
    client.post(f"/api/v1/me/invitations/{inv_id}/accept", headers=guest_headers)

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
    # "other"가 이 그룹의 일반 멤버여야 "멤버는 못 한다"를 실제로 검증한다.
    # 그룹에 속하지 않은 사람은 require_group_admin에서 더 앞서 GROUP_ACCESS_FORBIDDEN으로
    # 걸러지므로, 이 테스트의 의도(관리자가 아닌 멤버의 거부)를 재현하지 못했었다.
    client.post(
        f"/api/v1/groups/{group['id']}/members",
        json={"user_id": other_id},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    res = client.post(
        f"/api/v1/groups/{group['id']}/members",
        json={"user_id": member_id},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "GROUP_MEMBER_ADD_FORBIDDEN"


def test_outsider_cannot_add_member(client):
    """이 그룹에 아예 속하지 않은 사람은 require_group_admin의 멤버십
    검사에서 먼저 걸러져 일반 GROUP_ACCESS_FORBIDDEN을 받는다."""
    admin_token, _ = _signup(client, "admin@onque.dev")
    _, member_id = _signup(client, "member@onque.dev")
    outsider_token, _ = _signup(client, "outsider@onque.dev")
    group = client.post(
        "/api/v1/groups",
        json={"name": "행사기획팀"},
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()["data"]

    res = client.post(
        f"/api/v1/groups/{group['id']}/members",
        json={"user_id": member_id},
        headers={"Authorization": f"Bearer {outsider_token}"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "GROUP_ACCESS_FORBIDDEN"


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
    other_token, other_id = _signup(client, "other@onque.dev")
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
    # "other"가 이 그룹의 일반 멤버여야 "멤버는 못 한다"를 실제로 검증한다.
    # 그룹에 속하지 않은 사람은 require_group_admin에서 더 앞서 GROUP_ACCESS_FORBIDDEN으로
    # 걸러지므로, 이 테스트의 의도(관리자가 아닌 멤버의 거부)를 재현하지 못했었다.
    client.post(
        f"/api/v1/groups/{group['id']}/members",
        json={"user_id": other_id},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    res = client.delete(
        f"/api/v1/groups/{group['id']}/members/{member_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "GROUP_MEMBER_ADD_FORBIDDEN"


def test_outsider_cannot_remove_member(client):
    """이 그룹에 아예 속하지 않은 사람은 require_group_admin의 멤버십
    검사에서 먼저 걸러져 일반 GROUP_ACCESS_FORBIDDEN을 받는다."""
    admin_token, _ = _signup(client, "admin@onque.dev")
    _, member_id = _signup(client, "member@onque.dev")
    outsider_token, _ = _signup(client, "outsider@onque.dev")
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
        headers={"Authorization": f"Bearer {outsider_token}"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "GROUP_ACCESS_FORBIDDEN"


def test_member_list_returns_membership_role_not_user_role(client):
    """필드명이 role 그대로라 값의 의미가 조용히 바뀐다. 테스트로 고정한다."""
    owner = _signup_headers(client, "own@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    client.post(f"/api/v1/groups/{gid}/invitations", json={"email": "mem@t.dev"}, headers=owner)
    member = _signup_headers(client, "mem@t.dev", "멤버")
    # 초대만으로는 합류하지 않는다. 수락해야 멤버가 된다.
    inv_id = client.get("/api/v1/me/invitations", headers=member).json()["data"][0]["id"]
    client.post(f"/api/v1/me/invitations/{inv_id}/accept", headers=member)

    rows = client.get(f"/api/v1/groups/{gid}/members", headers=owner).json()["data"]
    assert {r["email"]: r["role"] for r in rows} == {"own@t.dev": "admin", "mem@t.dev": "member"}


def test_member_cannot_invite(client):
    owner = _signup_headers(client, "own2@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    client.post(f"/api/v1/groups/{gid}/invitations", json={"email": "mem2@t.dev"}, headers=owner)
    member = _signup_headers(client, "mem2@t.dev", "멤버")
    # 초대만으로는 합류하지 않는다. 수락해야 멤버가 된다.
    inv_id = client.get("/api/v1/me/invitations", headers=member).json()["data"][0]["id"]
    client.post(f"/api/v1/me/invitations/{inv_id}/accept", headers=member)

    res = client.post(
        f"/api/v1/groups/{gid}/invitations", json={"email": "x@t.dev"}, headers=member
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "GROUP_INVITE_FORBIDDEN"


def test_member_can_see_pending_invitations(client):
    """초대는 못 하지만 누가 대기 중인지는 볼 수 있다 — 기존 동작."""
    owner = _signup_headers(client, "own3@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    client.post(f"/api/v1/groups/{gid}/invitations", json={"email": "mem3@t.dev"}, headers=owner)
    member = _signup_headers(client, "mem3@t.dev", "멤버")
    # 초대만으로는 합류하지 않는다. 수락해야 멤버가 된다.
    inv_id = client.get("/api/v1/me/invitations", headers=member).json()["data"][0]["id"]
    client.post(f"/api/v1/me/invitations/{inv_id}/accept", headers=member)

    assert client.get(f"/api/v1/groups/{gid}/invitations", headers=member).status_code == 200


def test_outsider_gets_403_not_404_for_unknown_group(client):
    """404로 나누면 그룹 id의 존재 여부가 새어나간다."""
    headers = _signup_headers(client, "out@t.dev", "외부")
    assert client.get("/api/v1/groups/99999/members", headers=headers).status_code == 403


def test_invite_response_is_identical_for_registered_and_unregistered(client):
    """이 변경의 존재 이유. 응답이 다르면 임의 이메일의 가입 여부를 알아낼 수 있다."""
    owner = _signup_headers(client, "enum-own@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    _signup_headers(client, "enum-registered@t.dev", "가입자")

    registered = client.post(
        f"/api/v1/groups/{gid}/invitations",
        json={"email": "enum-registered@t.dev"},
        headers=owner,
    )
    unregistered = client.post(
        f"/api/v1/groups/{gid}/invitations",
        json={"email": "enum-stranger@t.dev"},
        headers=owner,
    )

    assert registered.status_code == unregistered.status_code == 200
    assert registered.json()["data"] == {"status": "invited", "email": "enum-registered@t.dev"}
    assert unregistered.json()["data"] == {"status": "invited", "email": "enum-stranger@t.dev"}
    # 이메일 값 외에는 키 구성이 완전히 같아야 한다
    assert set(registered.json()["data"]) == set(unregistered.json()["data"])


def test_inviting_a_registered_user_does_not_join_them(client):
    owner = _signup_headers(client, "noauto-own@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    guest = _signup_headers(client, "noauto-guest@t.dev", "손님")

    client.post(
        f"/api/v1/groups/{gid}/invitations",
        json={"email": "noauto-guest@t.dev"},
        headers=owner,
    )

    assert client.get("/api/v1/me", headers=guest).json()["data"]["groups"] == []
    rows = client.get("/api/v1/me/invitations", headers=guest).json()["data"]
    assert [r["group_id"] for r in rows] == [gid]


def test_signing_up_with_an_invited_email_does_not_auto_join(client):
    """가입 자체를 동의로 보지 않는다. 규칙은 하나 — 누구든 수락해야 들어간다."""
    owner = _signup_headers(client, "nosignup-own@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    client.post(
        f"/api/v1/groups/{gid}/invitations",
        json={"email": "nosignup-new@t.dev"},
        headers=owner,
    )

    newcomer = _signup_headers(client, "nosignup-new@t.dev", "신규")

    assert client.get("/api/v1/me", headers=newcomer).json()["data"]["groups"] == []
    rows = client.get("/api/v1/me/invitations", headers=newcomer).json()["data"]
    assert [r["group_id"] for r in rows] == [gid]


def test_cannot_remove_the_last_admin(client):
    """전역 admin이 사라졌으므로, 마지막 관리자가 빠지면 그 팀은 아무도
    초대할 수 없는 복구 불가 상태가 된다."""
    owner = _signup_headers(client, "last@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    me = client.get("/api/v1/me", headers=owner).json()["data"]["user"]

    res = client.delete(f"/api/v1/groups/{gid}/members/{me['id']}", headers=owner)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "GROUP_LAST_ADMIN"
