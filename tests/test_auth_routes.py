def test_signup_response_no_longer_exposes_global_role(client):
    """역할은 그룹 소속 속성이 됐다. 사용자 객체에 role이 남아 있으면
    프론트가 계속 그걸 읽어 잘못된 관리자 UI를 띄운다."""
    res = client.post(
        "/api/v1/auth/signup",
        json={"email": "norole@t.dev", "password": "password123", "name": "역할없음"},
    )
    assert "role" not in res.json()["data"]["user"]


def test_signup_then_explicit_group_creation_shows_up_in_me(client):
    """더 이상 가입만으로 그룹이 생기지 않는다. 명시적으로 만들어야
    /me에 나타난다."""
    signup = client.post(
        "/api/v1/auth/signup",
        json={"email": "admin@onque.dev", "password": "password123", "name": "관리자"},
    )
    token = signup.json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/api/v1/groups", json={"name": "기본 그룹"}, headers=headers)

    res = client.get("/api/v1/me", headers=headers)
    groups = res.json()["data"]["groups"]
    assert len(groups) == 1
    assert groups[0]["name"] == "기본 그룹"


def test_signup_second_user_has_no_group_until_invited(client):
    client.post(
        "/api/v1/auth/signup",
        json={"email": "admin@onque.dev", "password": "password123", "name": "관리자"},
    )
    signup = client.post(
        "/api/v1/auth/signup",
        json={"email": "member@onque.dev", "password": "password123", "name": "직원"},
    )
    token = signup.json()["data"]["token"]

    res = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert res.json()["data"]["groups"] == []


def test_signup_duplicate_email_returns_409(client):
    payload = {"email": "dup@onque.dev", "password": "password123", "name": "중복"}
    client.post("/api/v1/auth/signup", json=payload)
    res = client.post("/api/v1/auth/signup", json=payload)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "USER_EMAIL_DUPLICATE"


def test_signup_short_password_returns_422(client):
    res = client.post(
        "/api/v1/auth/signup",
        json={"email": "short@onque.dev", "password": "1234567", "name": "짧은비번"},
    )
    assert res.status_code == 422


def test_signup_invalid_email_returns_422(client):
    res = client.post(
        "/api/v1/auth/signup",
        json={"email": "not-an-email", "password": "password123", "name": "잘못된이메일"},
    )
    assert res.status_code == 422


def test_signup_empty_name_returns_422(client):
    res = client.post(
        "/api/v1/auth/signup",
        json={"email": "noname@onque.dev", "password": "password123", "name": ""},
    )
    assert res.status_code == 422


def test_login_success_returns_token(client):
    client.post(
        "/api/v1/auth/signup",
        json={"email": "login@onque.dev", "password": "password123", "name": "로그인"},
    )
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "login@onque.dev", "password": "password123"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["token"]


def test_login_wrong_password_returns_401(client):
    client.post(
        "/api/v1/auth/signup",
        json={"email": "wrong@onque.dev", "password": "password123", "name": "테스트"},
    )
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "wrong@onque.dev", "password": "incorrect"},
    )
    assert res.status_code == 401


def test_me_requires_auth_header(client):
    res = client.get("/api/v1/me")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "AUTH_TOKEN_INVALID"


def test_me_returns_current_user_and_groups(client):
    signup = client.post(
        "/api/v1/auth/signup",
        json={"email": "me@onque.dev", "password": "password123", "name": "나"},
    )
    token = signup.json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/api/v1/groups", json={"name": "내 그룹"}, headers=headers)

    res = client.get("/api/v1/me", headers=headers)
    assert res.status_code == 200
    assert res.json()["data"]["user"]["email"] == "me@onque.dev"
    assert [g["name"] for g in res.json()["data"]["groups"]] == ["내 그룹"]


def _signup(client, email, name):
    res = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "password123", "name": name},
    )
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['data']['token']}"}


def test_me_reports_role_per_group(client):
    a = _signup(client, "p1@t.dev", "A")
    b = _signup(client, "p2@t.dev", "B")
    gid_b = client.post("/api/v1/groups", json={"name": "B팀"}, headers=b).json()["data"]["id"]
    client.post(f"/api/v1/groups/{gid_b}/invitations", json={"email": "p1@t.dev"}, headers=b)
    # 초대만으로는 합류하지 않는다. 수락해야 멤버가 된다.
    inv_id = client.get("/api/v1/me/invitations", headers=a).json()["data"][0]["id"]
    client.post(f"/api/v1/me/invitations/{inv_id}/accept", headers=a)
    gid_a = client.post("/api/v1/groups", json={"name": "A팀"}, headers=a).json()["data"]["id"]

    groups = client.get("/api/v1/me", headers=a).json()["data"]["groups"]
    assert {g["id"]: g["role"] for g in groups} == {gid_a: "admin", gid_b: "member"}


def test_me_includes_created_at(client):
    headers = _signup(client, "p3@t.dev", "C")
    assert "created_at" in client.get("/api/v1/me", headers=headers).json()["data"]["user"]


def test_can_change_my_name(client):
    headers = _signup(client, "p4@t.dev", "옛이름")
    assert client.patch("/api/v1/me", json={"name": "새이름"}, headers=headers).status_code == 200
    assert client.get("/api/v1/me", headers=headers).json()["data"]["user"]["name"] == "새이름"


def test_password_change_requires_the_current_password(client):
    """현재 비밀번호를 확인하지 않으면 탈취된 토큰이 곧 계정 탈취다."""
    headers = _signup(client, "p5@t.dev", "D")
    res = client.post(
        "/api/v1/me/password",
        json={"current_password": "wrongpassword", "new_password": "newpassword123"},
        headers=headers,
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "USER_PASSWORD_INVALID"


def test_password_change_succeeds_and_old_password_stops_working(client):
    headers = _signup(client, "p6@t.dev", "E")
    assert client.post(
        "/api/v1/me/password",
        json={"current_password": "password123", "new_password": "newpassword123"},
        headers=headers,
    ).status_code == 200

    assert client.post(
        "/api/v1/auth/login", json={"email": "p6@t.dev", "password": "password123"}
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/login", json={"email": "p6@t.dev", "password": "newpassword123"}
    ).status_code == 200


def test_global_user_list_endpoint_is_gone(client):
    """다른 조직 사용자의 이메일이 새어나가는 구멍이었고 쓰는 화면도 없었다."""
    headers = _signup(client, "p7@t.dev", "F")
    assert client.get("/api/v1/users", headers=headers).status_code == 404


def _make_pending_invitation(db_session, group_id: int, email: str, invited_by: int) -> int:
    """대기 초대를 직접 만든다. 초대 엔드포인트는 Task 2 전까지 가입자를 즉시
    합류시키므로, 대기 상태를 만들려면 행을 직접 넣어야 한다."""
    from models import GroupInvitation

    inv = GroupInvitation(group_id=group_id, email=email, invited_by=invited_by)
    db_session.add(inv)
    db_session.commit()
    return inv.id


def test_my_invitations_lists_only_mine(client, db_session):
    owner = _signup(client, "inv-own@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    owner_id = client.get("/api/v1/me", headers=owner).json()["data"]["user"]["id"]

    guest = _signup(client, "inv-guest@t.dev", "손님")
    _signup(client, "inv-other@t.dev", "남")
    _make_pending_invitation(db_session, gid, "inv-guest@t.dev", owner_id)
    _make_pending_invitation(db_session, gid, "inv-other@t.dev", owner_id)

    rows = client.get("/api/v1/me/invitations", headers=guest).json()["data"]
    assert [r["group_id"] for r in rows] == [gid]
    assert rows[0]["group_name"] == "A팀"
    assert rows[0]["invited_by_name"] == "주인"


def test_invitation_is_not_membership_until_accepted(client, db_session):
    """이 변경의 존재 이유. 초대만으로 팀에 들어가면 안 된다."""
    owner = _signup(client, "inv2-own@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    owner_id = client.get("/api/v1/me", headers=owner).json()["data"]["user"]["id"]

    guest = _signup(client, "inv2-guest@t.dev", "손님")
    _make_pending_invitation(db_session, gid, "inv2-guest@t.dev", owner_id)

    assert client.get("/api/v1/me", headers=guest).json()["data"]["groups"] == []


def test_accepting_an_invitation_joins_as_member(client, db_session):
    owner = _signup(client, "inv3-own@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    owner_id = client.get("/api/v1/me", headers=owner).json()["data"]["user"]["id"]

    guest = _signup(client, "inv3-guest@t.dev", "손님")
    inv_id = _make_pending_invitation(db_session, gid, "inv3-guest@t.dev", owner_id)

    assert client.post(f"/api/v1/me/invitations/{inv_id}/accept", headers=guest).status_code == 200

    groups = client.get("/api/v1/me", headers=guest).json()["data"]["groups"]
    assert [(g["id"], g["role"]) for g in groups] == [(gid, "member")]
    assert client.get("/api/v1/me/invitations", headers=guest).json()["data"] == []


def test_declining_removes_the_invitation_without_joining(client, db_session):
    owner = _signup(client, "inv4-own@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    owner_id = client.get("/api/v1/me", headers=owner).json()["data"]["user"]["id"]

    guest = _signup(client, "inv4-guest@t.dev", "손님")
    inv_id = _make_pending_invitation(db_session, gid, "inv4-guest@t.dev", owner_id)

    assert client.delete(f"/api/v1/me/invitations/{inv_id}", headers=guest).status_code == 200
    assert client.get("/api/v1/me/invitations", headers=guest).json()["data"] == []
    assert client.get("/api/v1/me", headers=guest).json()["data"]["groups"] == []


def test_cannot_accept_someone_elses_invitation(client, db_session):
    """403으로 나누면 초대 id의 존재 여부가 새어나간다."""
    owner = _signup(client, "inv5-own@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    owner_id = client.get("/api/v1/me", headers=owner).json()["data"]["user"]["id"]

    _signup(client, "inv5-target@t.dev", "대상")
    attacker = _signup(client, "inv5-attacker@t.dev", "공격")
    inv_id = _make_pending_invitation(db_session, gid, "inv5-target@t.dev", owner_id)

    res = client.post(f"/api/v1/me/invitations/{inv_id}/accept", headers=attacker)
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "INVITATION_NOT_FOUND"
    assert client.delete(f"/api/v1/me/invitations/{inv_id}", headers=attacker).status_code == 404


def test_accepting_twice_is_not_found_the_second_time(client, db_session):
    owner = _signup(client, "inv6-own@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    owner_id = client.get("/api/v1/me", headers=owner).json()["data"]["user"]["id"]

    guest = _signup(client, "inv6-guest@t.dev", "손님")
    inv_id = _make_pending_invitation(db_session, gid, "inv6-guest@t.dev", owner_id)

    assert client.post(f"/api/v1/me/invitations/{inv_id}/accept", headers=guest).status_code == 200
    assert client.post(f"/api/v1/me/invitations/{inv_id}/accept", headers=guest).status_code == 404


def test_invitation_email_matching_ignores_case(client, db_session):
    """가입 컬럼은 대소문자를 구분해 저장한다. 초대 이메일도 마찬가지다."""
    owner = _signup(client, "inv7-own@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    owner_id = client.get("/api/v1/me", headers=owner).json()["data"]["user"]["id"]

    guest = _signup(client, "inv7-Guest@t.dev", "손님")
    _make_pending_invitation(db_session, gid, "inv7-guest@t.dev", owner_id)

    assert len(client.get("/api/v1/me/invitations", headers=guest).json()["data"]) == 1


def test_invitation_endpoints_require_auth(client):
    """토큰 없이 부르면 401이고, 봉투 형식(success: false, error.code)을 지켜야 한다."""
    for res in (
        client.get("/api/v1/me/invitations"),
        client.post("/api/v1/me/invitations/1/accept"),
        client.delete("/api/v1/me/invitations/1"),
    ):
        assert res.status_code == 401
        body = res.json()
        assert body["success"] is False
        assert body["error"]["code"]


def test_accepting_a_declined_invitation_is_not_found(client, db_session):
    """거절한 초대는 행이 삭제되므로 같은 id로 다시 수락하면 404다."""
    owner = _signup(client, "inv8-own@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    owner_id = client.get("/api/v1/me", headers=owner).json()["data"]["user"]["id"]

    guest = _signup(client, "inv8-guest@t.dev", "손님")
    inv_id = _make_pending_invitation(db_session, gid, "inv8-guest@t.dev", owner_id)

    assert client.delete(f"/api/v1/me/invitations/{inv_id}", headers=guest).status_code == 200

    res = client.post(f"/api/v1/me/invitations/{inv_id}/accept", headers=guest)
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "INVITATION_NOT_FOUND"


def test_accepting_with_different_email_case_succeeds(client, db_session):
    """초대 이메일과 가입 이메일의 대소문자가 달라도 소유권 검사가 통과해야 한다."""
    owner = _signup(client, "inv9-own@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    owner_id = client.get("/api/v1/me", headers=owner).json()["data"]["user"]["id"]

    guest = _signup(client, "inv9-Guest@t.dev", "손님")
    inv_id = _make_pending_invitation(db_session, gid, "inv9-guest@t.dev", owner_id)

    res = client.post(f"/api/v1/me/invitations/{inv_id}/accept", headers=guest)
    assert res.status_code == 200

    groups = client.get("/api/v1/me", headers=guest).json()["data"]["groups"]
    assert [g["id"] for g in groups] == [gid]


def test_accepting_invitation_when_already_a_member_is_idempotent(client, db_session):
    """다른 경로로 이미 그 그룹 멤버인 상태에서 대기 초대를 수락해도 500이 아니라
    정상 처리돼야 한다 — join_group은 멱등하다."""
    from models import GroupMembership

    owner = _signup(client, "inv10-own@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    owner_id = client.get("/api/v1/me", headers=owner).json()["data"]["user"]["id"]

    guest = _signup(client, "inv10-guest@t.dev", "손님")
    guest_id = client.get("/api/v1/me", headers=guest).json()["data"]["user"]["id"]
    inv_id = _make_pending_invitation(db_session, gid, "inv10-guest@t.dev", owner_id)

    db_session.add(GroupMembership(user_id=guest_id, group_id=gid, role="member"))
    db_session.commit()

    res = client.post(f"/api/v1/me/invitations/{inv_id}/accept", headers=guest)
    assert res.status_code == 200
    assert res.json()["data"]["group_id"] == gid
