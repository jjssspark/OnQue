"""비서 엔드포인트.

이 엔드포인트는 읽기 전용이다 — 실제 변경은 프론트가 기존 엔드포인트로 한다.
권한 검사와 전이 규칙을 두 벌로 유지하지 않기 위해서다.
"""

import gemini_service
from models import Commitment, Schedule, Todo


def _signup(client, email, name):
    return client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "password123", "name": name},
    ).json()["data"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _setup(client):
    owner = _signup(client, "owner@onque.dev", "주인")
    group_id = client.post(
        "/api/v1/groups", json={"name": "A팀"}, headers=_auth(owner["token"])
    ).json()["data"]["id"]
    return owner, group_id


def _ask(client, token, group_id, message="약속 뭐 있지?", history=None):
    return client.post(
        "/api/v1/assistant/messages",
        json={"group_id": group_id, "message": message, "history": history or []},
        headers=_auth(token),
    )


def test_answers_with_envelope(client, monkeypatch):
    owner, group_id = _setup(client)
    monkeypatch.setattr(
        gemini_service, "answer_assistant",
        lambda ctx, hist, msg, **kw: {"reply": "약속은 없습니다.", "actions": []},
    )

    res = _ask(client, owner["token"], group_id)

    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["reply"] == "약속은 없습니다."
    assert body["data"]["actions"] == []
    assert body["error"] is None


def test_non_member_gets_403(client, monkeypatch):
    owner, group_id = _setup(client)
    outsider = _signup(client, "outsider@onque.dev", "외부인")
    monkeypatch.setattr(
        gemini_service, "answer_assistant",
        lambda ctx, hist, msg, **kw: {"reply": "여기 오면 안 된다", "actions": []},
    )

    res = _ask(client, outsider["token"], group_id)

    assert res.status_code == 403
    assert res.json()["error"]["code"] == "GROUP_ACCESS_FORBIDDEN"


def test_gemini_failure_returns_502_envelope(client, monkeypatch):
    """실패를 조용히 넘기면 '답이 없음'과 '모델이 죽음'이 구분되지 않는다."""
    owner, group_id = _setup(client)
    monkeypatch.setattr(gemini_service, "answer_assistant", lambda ctx, hist, msg, **kw: None)

    res = _ask(client, owner["token"], group_id)

    assert res.status_code == 502
    assert res.json()["error"]["code"] == "ASSISTANT_UNAVAILABLE"


def test_quota_exhaustion_returns_429_with_its_own_code(client, monkeypatch):
    """한도 소진은 502가 아니라 429다. 502 문구("잠시 후 다시 시도해주세요")를
    그대로 쓰면 사용량이 초기화될 때까지 계속 실패하는데도 사용자가 재시도를
    반복한다."""
    owner, group_id = _setup(client)

    def boom(ctx, hist, msg, **kwargs):
        raise gemini_service.QuotaExceeded()

    monkeypatch.setattr(gemini_service, "answer_assistant", boom)

    res = _ask(client, owner["token"], group_id)

    assert res.status_code == 429
    assert res.json()["error"]["code"] == "ASSISTANT_QUOTA_EXCEEDED"
    assert "잠시 후" not in res.json()["error"]["message"]


def test_history_is_capped_not_rejected(client, monkeypatch):
    """상한 초과는 사용자 잘못이 아니다. 422로 거절하지 않고 서버가 자른다."""
    import assistant_service

    owner, group_id = _setup(client)
    captured = {}

    def fake(ctx, hist, msg, **kwargs):
        captured["history"] = hist
        return {"reply": "네", "actions": []}

    monkeypatch.setattr(gemini_service, "answer_assistant", fake)
    long_history = [{"role": "user", "content": f"메시지 {i}"} for i in range(40)]

    res = _ask(client, owner["token"], group_id, history=long_history)

    assert res.status_code == 200
    assert len(captured["history"]) == assistant_service.HISTORY_MESSAGE_LIMIT
    # 잘라내되 최근 것을 남긴다.
    assert captured["history"][-1]["content"] == "메시지 39"


def test_empty_message_returns_422(client):
    owner, group_id = _setup(client)

    res = _ask(client, owner["token"], group_id, message="")

    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_FAILED"


def test_endpoint_does_not_write_to_db(client, db_session, monkeypatch):
    """비서 엔드포인트는 읽기 전용이다."""
    owner, group_id = _setup(client)
    db_session.add(Todo(group_id=group_id, content="그대로 남을 일"))
    db_session.commit()

    before = (
        db_session.query(Todo).count(),
        db_session.query(Schedule).count(),
        db_session.query(Commitment).count(),
    )

    # 모델이 삭제를 제안해도 엔드포인트는 실행하지 않는다.
    todo_id = db_session.query(Todo).first().id
    monkeypatch.setattr(
        gemini_service, "answer_assistant",
        lambda ctx, hist, msg, **kw: {
            "reply": "지울까요?",
            "actions": [{"kind": "todo_delete", "todo_id": todo_id}],
        },
    )

    res = _ask(client, owner["token"], group_id, message="그거 지워줘")

    assert res.status_code == 200
    assert res.json()["data"]["actions"][0]["risk"] == "confirm"
    db_session.expire_all()
    after = (
        db_session.query(Todo).count(),
        db_session.query(Schedule).count(),
        db_session.query(Commitment).count(),
    )
    assert before == after


def test_dropped_actions_are_reported_in_reply(client, monkeypatch):
    """조용히 사라지면 사용자는 비서가 무시했다고 생각한다."""
    owner, group_id = _setup(client)
    monkeypatch.setattr(
        gemini_service, "answer_assistant",
        lambda ctx, hist, msg, **kw: {
            "reply": "지우겠습니다.",
            "actions": [{"kind": "todo_delete", "todo_id": 99999}],
        },
    )

    res = _ask(client, owner["token"], group_id, message="그거 지워줘")

    body = res.json()["data"]
    assert body["actions"] == []
    assert "제외" in body["reply"]
