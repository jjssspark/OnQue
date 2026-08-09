"""봉투(envelope) 밖으로 새는 응답을 막는다.

프론트는 `error.code`로 분기한다(api-contract.md). 그런데 라우터가 직접 만들지
않은 응답 — 없는 경로(404), 잘못된 메서드(405), 검증 실패(422), 처리 못 한 예외
(500) — 는 봉투를 거치지 않아 `{"detail": ...}` 또는 스택 트레이스로 나갔다.
프론트 입장에선 `error.code`가 없으니 분기가 불가능하고, 500은 내부 경로까지
흘린다.
"""

from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from main import app


def _signup(client, email, name):
    return client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "password123", "name": name},
    ).json()["data"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _assert_envelope(body):
    """봉투의 세 칸이 모두 있고 data/error 중 정확히 한쪽만 채워졌는지."""
    assert set(body) >= {"success", "data", "error"}
    assert body["success"] is False
    assert body["data"] is None
    assert isinstance(body["error"], dict)
    assert body["error"].get("code")
    assert body["error"].get("message")


def test_unknown_route_returns_envelope(client):
    res = client.get("/api/v1/does-not-exist")

    assert res.status_code == 404
    _assert_envelope(res.json())
    assert res.json()["error"]["code"] == "NOT_FOUND"


def test_method_not_allowed_returns_envelope(client):
    """GET/PATCH만 있는 /me에 DELETE를 보낸다.

    Starlette 라우터가 던지는 것은 starlette.exceptions.HTTPException이고,
    FastAPI의 HTTPException은 그 하위 클래스다. 핸들러를 하위 클래스에만
    걸어두면 이 405가 핸들러를 그냥 지나쳐 봉투 밖으로 나간다.
    """
    res = client.delete("/api/v1/me")

    assert res.status_code == 405
    _assert_envelope(res.json())
    assert res.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_validation_error_returns_envelope_with_field_details(client):
    res = client.post(
        "/api/v1/auth/signup",
        json={"email": "not-an-email", "password": "short", "name": "이름"},
    )

    assert res.status_code == 422
    body = res.json()
    _assert_envelope(body)
    assert body["error"]["code"] == "VALIDATION_FAILED"

    # 어느 필드가 왜 틀렸는지는 details로 내려간다. 메시지 문자열을 파싱하게
    # 만들면 프론트가 서버 문구 변경에 깨진다.
    fields = {d["field"] for d in body["error"]["details"]}
    assert fields == {"email", "password"}


def test_unhandled_exception_returns_envelope_without_internals(client):
    """500에 스택 트레이스나 내부 경로를 담지 않는다 (api-contract.md)."""
    boom = RuntimeError("psycopg2 연결 실패: host=10.0.0.5 password=hunter2")
    admin = _signup(client, "admin@onque.dev", "관리자")

    with patch("routers.auth.get_user_groups_with_role", side_effect=boom):
        # TestClient는 기본적으로 서버 예외를 그대로 다시 던져 핸들러를 못 보게 한다.
        with TestClient(app, raise_server_exceptions=False) as raw:
            res = raw.get("/api/v1/me", headers=_auth(admin["token"]))

    assert res.status_code == 500
    body = res.json()
    _assert_envelope(body)
    assert body["error"]["code"] == "INTERNAL_ERROR"

    leaked = res.text
    assert "psycopg2" not in leaked
    assert "hunter2" not in leaked
    assert "Traceback" not in leaked
    assert "routers/auth.py" not in leaked


def test_duplicate_invitation_race_returns_409_not_500(client):
    """같은 이메일 초대가 동시에 들어와 유니크 제약에 걸리면 409로 답한다.

    순차 실행이었다면 뒤에 온 쪽은 사전 검사에서 GROUP_INVITE_ALREADY_SENT를
    받았을 것이다. 경쟁에서 진 요청도 같은 답을 줘야 한다.

    한계: 인메모리 SQLite 단일 스레드라 실제 동시 삽입을 재현할 수 없다.
    삽입이 IntegrityError를 던졌을 때 그것이 봉투 밖 500이 아니라 409가
    되는지를 검증한다.
    """
    admin = _signup(client, "admin@onque.dev", "관리자")
    group_id = client.post(
        "/api/v1/groups", json={"name": "A팀"}, headers=_auth(admin["token"])
    ).json()["data"]["id"]

    dup = IntegrityError("INSERT ...", {}, Exception("uq_group_invitations_group_email"))
    with patch("routers.groups._upsert_invitation", side_effect=dup):
        res = client.post(
            f"/api/v1/groups/{group_id}/invitations",
            json={"email": "newbie@onque.dev"},
            headers=_auth(admin["token"]),
        )

    assert res.status_code == 409
    _assert_envelope(res.json())
    assert res.json()["error"]["code"] == "GROUP_INVITE_ALREADY_SENT"
