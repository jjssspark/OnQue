def test_signup_first_user_becomes_admin(client):
    res = client.post(
        "/api/v1/auth/signup",
        json={"email": "admin@onque.dev", "password": "password123", "name": "관리자"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["user"]["role"] == "admin"
    assert body["data"]["token"]


def test_signup_first_user_gets_default_group(client):
    signup = client.post(
        "/api/v1/auth/signup",
        json={"email": "admin@onque.dev", "password": "password123", "name": "관리자"},
    )
    token = signup.json()["data"]["token"]

    res = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
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


def test_signup_second_user_becomes_member(client):
    client.post(
        "/api/v1/auth/signup",
        json={"email": "admin@onque.dev", "password": "password123", "name": "관리자"},
    )
    res = client.post(
        "/api/v1/auth/signup",
        json={"email": "member@onque.dev", "password": "password123", "name": "직원"},
    )
    assert res.json()["data"]["user"]["role"] == "member"


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
    res = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["data"]["user"]["email"] == "me@onque.dev"
    # 첫 가입자이므로 기본 그룹이 함께 생성된다.
    assert [g["name"] for g in res.json()["data"]["groups"]] == ["기본 그룹"]
