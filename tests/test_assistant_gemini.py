"""비서 모델 호출. 실제 Gemini를 부르지 않고 client를 목으로 막는다."""

import json
from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors

import gemini_service


def _fake_response(payload):
    return SimpleNamespace(text=json.dumps(payload))


def test_answer_assistant_returns_reply_and_actions(monkeypatch):
    captured = {}

    def fake_generate(*, model, contents, config):
        captured["contents"] = contents
        return _fake_response(
            {"reply": "약속은 2건입니다.", "actions": [{"kind": "todo_add", "content": "시안 정리"}]}
        )

    monkeypatch.setattr(gemini_service.client.models, "generate_content", fake_generate)

    result = gemini_service.answer_assistant("[약속]\n- id=1 | 시안", [], "약속 뭐 있지?")

    assert result["reply"] == "약속은 2건입니다."
    assert result["actions"][0]["kind"] == "todo_add"
    # 컨텍스트와 질문이 프롬프트에 실려야 한다.
    assert "id=1" in captured["contents"]
    assert "약속 뭐 있지?" in captured["contents"]


def test_answer_assistant_includes_history(monkeypatch):
    captured = {}

    def fake_generate(*, model, contents, config):
        captured["contents"] = contents
        return _fake_response({"reply": "네", "actions": []})

    monkeypatch.setattr(gemini_service.client.models, "generate_content", fake_generate)

    gemini_service.answer_assistant(
        "ctx",
        [{"role": "user", "content": "앞선 질문"}, {"role": "assistant", "content": "앞선 답"}],
        "그래서?",
    )

    assert "앞선 질문" in captured["contents"]
    assert "앞선 답" in captured["contents"]


def test_answer_assistant_returns_none_on_failure(monkeypatch):
    """실패를 빈 답으로 뭉개면 '모델이 죽음'과 '할 말 없음'이 구분되지 않는다."""

    def explode(*args, **kwargs):
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(gemini_service.client.models, "generate_content", explode)

    assert gemini_service.answer_assistant("ctx", [], "질문") is None


def test_answer_assistant_returns_none_on_malformed_json(monkeypatch):
    monkeypatch.setattr(
        gemini_service.client.models,
        "generate_content",
        lambda **kwargs: SimpleNamespace(text="이건 JSON이 아니다"),
    )

    assert gemini_service.answer_assistant("ctx", [], "질문") is None


def _client_error(code):
    return genai_errors.ClientError(
        code,
        {"error": {"code": code, "message": "quota", "status": "RESOURCE_EXHAUSTED"}},
    )


def test_quota_exceeded_is_raised_not_swallowed(monkeypatch):
    """429는 None으로 뭉개면 안 된다. 일시적 오류와 달리 사용량이 초기화될
    때까지 계속 실패해서, 호출자가 "잠시 후 다시"와 다른 안내를 해야 한다."""
    def boom(**kwargs):
        raise _client_error(429)

    monkeypatch.setattr(gemini_service.client.models, "generate_content", boom)

    with pytest.raises(gemini_service.QuotaExceeded):
        gemini_service.answer_assistant("ctx", [], "질문")


def test_other_client_errors_still_return_none(monkeypatch):
    """한도만 구분한다. 나머지 실패는 종전대로 None이라 502로 나간다."""
    def boom(**kwargs):
        raise _client_error(400)

    monkeypatch.setattr(gemini_service.client.models, "generate_content", boom)

    assert gemini_service.answer_assistant("ctx", [], "질문") is None


def test_actions_default_to_empty_list(monkeypatch):
    monkeypatch.setattr(
        gemini_service.client.models,
        "generate_content",
        lambda **kwargs: _fake_response({"reply": "답만 있음"}),
    )

    result = gemini_service.answer_assistant("ctx", [], "질문")

    assert result == {"reply": "답만 있음", "actions": []}
