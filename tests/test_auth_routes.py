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


def test_me_returns_current_user_and_groups(client):
    signup = client.post(
        "/api/v1/auth/signup",
        json={"email": "me@onque.dev", "password": "password123", "name": "나"},
    )
    token = signup.json()["data"]["token"]
    res = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["data"]["user"]["email"] == "me@onque.dev"
    assert res.json()["data"]["groups"] == []
