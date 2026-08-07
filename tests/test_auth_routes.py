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
    # p1은 이미 가입돼 있으므로 초대 즉시 합류한다
    client.post(f"/api/v1/groups/{gid_b}/invitations", json={"email": "p1@t.dev"}, headers=b)
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
