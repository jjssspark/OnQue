import pytest
from google.genai import errors as genai_errors

import gemini_service
from models import ChatMessage, Document, Todo


def _setup(client):
    token = client.post(
        "/api/v1/auth/signup",
        json={"email": "admin@onque.dev", "password": "password123", "name": "관리자"},
    ).json()["data"]["token"]
    auth = {"Authorization": f"Bearer {token}"}
    group_id = client.post("/api/v1/groups", json={"name": "A팀"}, headers=auth).json()["data"]["id"]
    room = client.get("/chat/rooms", params={"group_id": group_id}, headers=auth).json()[0]
    return auth, group_id, room["id"]


def _say(client, auth, room_id, content, sender="관리자"):
    return client.post(
        "/chat/messages",
        params={"room_id": room_id},
        json={"sender": sender, "content": content},
        headers=auth,
    ).json()


def _fake_turn(reply="네, 확인했습니다.", **over):
    empty = {
        "add_todos": [],
        "complete_todo_hints": [],
        "delete_todo_hints": [],
        "add_schedules": [],
        "delete_schedule_hints": [],
    }
    return {**empty, **over, "reply": reply}


def test_plain_message_does_not_call_gemini_when_ai_is_absent(client, monkeypatch):
    auth, _, room_id = _setup(client)

    def explode(*args, **kwargs):
        raise AssertionError("AI가 없는 방에서 Gemini를 호출하면 안 된다")

    monkeypatch.setattr(gemini_service, "chat_reply_with_actions", explode)
    monkeypatch.setattr(gemini_service, "extract_chat_actions", explode)
    monkeypatch.setattr(gemini_service, "generate_bot_reply", explode)

    result = _say(client, auth, room_id, "점심 뭐 드실래요")

    assert result["bot_message"] is None
    assert result["ai_mode"] is False


def test_help_summons_ai_and_exit_dismisses_it(client, monkeypatch):
    auth, _, room_id = _setup(client)
    monkeypatch.setattr(gemini_service, "chat_reply_with_actions", lambda h, m, **kw: _fake_turn())

    entered = _say(client, auth, room_id, "/help")
    assert entered["ai_mode"] is True
    assert "/요약" in entered["bot_message"]["content"]

    # AI가 있는 동안에는 일반 메시지에도 답한다.
    chatting = _say(client, auth, room_id, "이번 주 목표 정리해줘")
    assert chatting["bot_message"]["content"] == "네, 확인했습니다."

    left = _say(client, auth, room_id, "/exit")
    assert left["ai_mode"] is False

    silent = _say(client, auth, room_id, "이제 우리끼리 얘기")
    assert silent["bot_message"] is None


def test_summary_command_posts_bot_summary(client, monkeypatch):
    auth, _, room_id = _setup(client)
    monkeypatch.setattr(gemini_service, "summarize_conversation", lambda msgs, **kw: "출시일을 확정했다.")

    result = _say(client, auth, room_id, "/요약")

    assert result["bot_message"]["content"] == "출시일을 확정했다."
    assert result["bot_message"]["is_bot"] is True
    # 요약은 AI를 상주시키지 않는다.
    assert result["ai_mode"] is False


def test_document_command_saves_a_document(client, monkeypatch, db_session):
    auth, _, room_id = _setup(client)
    structured = {
        "headline": "9월 출시 일정을 확정했다.",
        "key_points": ["베타는 8월 20일"],
        "requests": [],
        "action_items": [],
        "notes": "",
    }
    monkeypatch.setattr(
        gemini_service, "draft_document_from_conversation", lambda msgs, title, **kw: structured
    )
    monkeypatch.setattr(gemini_service, "classify_document_category", lambda text, **kw: "기획")

    result = _say(client, auth, room_id, "/문서 8월 첫째주 회의록")

    assert "8월 첫째주 회의록" in result["bot_message"]["content"]
    doc = db_session.query(Document).one()
    assert doc.filename == "8월 첫째주 회의록"
    assert doc.source_type == "document"
    assert "9월 출시 일정을 확정했다." in doc.summary


def test_document_command_reports_when_draft_fails(client, monkeypatch):
    auth, _, room_id = _setup(client)
    monkeypatch.setattr(
        gemini_service, "draft_document_from_conversation", lambda msgs, title, **kw: None
    )

    result = _say(client, auth, room_id, "/문서")

    assert "부족" in result["bot_message"]["content"]


def test_todo_command_registers_with_parsed_due_date(client, monkeypatch):
    auth, _, room_id = _setup(client)
    monkeypatch.setattr(
        gemini_service,
        "extract_chat_actions",
        lambda c, **kw: {"add_todos": [{"content": "견적서 제출", "due_date": "2026-08-12"}]},
    )

    result = _say(client, auth, room_id, "/할일 견적서 8월 12일까지")

    assert "견적서 제출" in result["bot_message"]["content"]
    assert [(t["content"], t["due_date"]) for t in result["todos"]] == [
        ("견적서 제출", "2026-08-12")
    ]


def test_todo_command_falls_back_to_raw_text(client, monkeypatch, db_session):
    auth, _, room_id = _setup(client)
    # 추출기가 아무것도 못 뽑아도 사용자가 적은 내용은 잃지 않는다.
    monkeypatch.setattr(gemini_service, "extract_chat_actions", lambda c, **kw: {"add_todos": []})

    _say(client, auth, room_id, "/할일 사무실 비품 주문")

    assert [t.content for t in db_session.query(Todo).all()] == ["사무실 비품 주문"]


def test_todo_command_without_argument_asks_for_content(client):
    auth, _, room_id = _setup(client)

    result = _say(client, auth, room_id, "/할일")

    assert "적어주세요" in result["bot_message"]["content"]


def test_ask_command_replies_without_entering_ai_mode(client, monkeypatch):
    auth, _, room_id = _setup(client)
    monkeypatch.setattr(gemini_service, "generate_bot_reply", lambda h, m, **kw: "A안이 더 빠릅니다.")

    result = _say(client, auth, room_id, "/질문 A안과 B안 차이가 뭐야")

    assert result["bot_message"]["content"] == "A안이 더 빠릅니다."
    assert result["ai_mode"] is False


def test_unknown_command_lists_available_ones(client):
    auth, _, room_id = _setup(client)

    result = _say(client, auth, room_id, "/없는명령")

    assert "모르는 명령" in result["bot_message"]["content"]
    assert "/help" in result["bot_message"]["content"]


def test_병합_호출은_답변과_액션을_한_번에_돌려준다(monkeypatch):
    """모델을 두 번 부르지 않고 한 응답에서 둘 다 받는다."""
    import json

    class FakeResponse:
        text = json.dumps(
            {
                "reply": "네, 내일까지 견적서 확인하겠습니다.",
                "add_todos": [{"content": "견적서 보내기", "due_date": "2026-08-18"}],
                "complete_todo_hints": [],
                "delete_todo_hints": [],
                "add_schedules": [],
                "delete_schedule_hints": [],
            }
        )

    calls = []

    def fake_generate(**kwargs):
        calls.append(kwargs)
        return FakeResponse()

    monkeypatch.setattr(gemini_service.client.models, "generate_content", fake_generate)

    result = gemini_service.chat_reply_with_actions(
        [{"sender": "김대리", "content": "안녕하세요"}],
        "내일까지 견적서 보낼게요",
        claim=lambda: True,
    )

    assert len(calls) == 1
    assert result["reply"] == "네, 내일까지 견적서 확인하겠습니다."
    assert result["add_todos"] == [{"content": "견적서 보내기", "due_date": "2026-08-18"}]
    assert result["complete_todo_hints"] == []


def test_병합_호출이_실패하면_답변도_액션도_없다(monkeypatch):
    """합친 대가다. 지금은 추출이 실패해도 답변은 나갔지만, 한 번에
    받으므로 한 번의 실패가 둘 다 잃는다. 대신 호출은 1건만 태운다."""

    def boom(**kwargs):
        raise RuntimeError("모델 실패")

    monkeypatch.setattr(gemini_service.client.models, "generate_content", boom)

    result = gemini_service.chat_reply_with_actions([], "아무 말", claim=lambda: True)

    assert result["reply"] == ""
    assert result["add_todos"] == []


def test_병합_호출이_빈_답변을_주면_빈_문자열이다(monkeypatch):
    """호출부가 빈 답변일 때 봇 메시지를 안 남기도록 판단할 수 있어야 한다."""
    import json

    class FakeResponse:
        text = json.dumps({"reply": "   ", "add_todos": []})

    monkeypatch.setattr(
        gemini_service.client.models, "generate_content", lambda **kw: FakeResponse()
    )

    result = gemini_service.chat_reply_with_actions([], "아무 말", claim=lambda: True)
    assert result["reply"] == ""
    assert result["add_todos"] == []


def _turn_response(**over):
    """모델이 돌려줄 법한 한 턴 응답. generate_content를 가짜로 바꿀 때 쓴다."""
    import json

    body = {
        "reply": "네, 확인했습니다.",
        "add_todos": [],
        "complete_todo_hints": [],
        "delete_todo_hints": [],
        "add_schedules": [],
        "delete_schedule_hints": [],
    }
    body.update(over)

    class FakeResponse:
        text = json.dumps(body)

    return FakeResponse()


def test_ai_모드_일반_메시지는_모델을_한_번만_부른다(client, monkeypatch):
    """이 태스크의 존재 이유다. 함수를 직접 부르는 대신 엔드포인트를 쳐서,
    호출부가 실제로 한 번만 태우는지 본다."""
    auth, _, room_id = _setup(client)
    _say(client, auth, room_id, "/help")

    calls = []

    def fake_generate(**kwargs):
        calls.append(kwargs)
        return _turn_response()

    monkeypatch.setattr(gemini_service.client.models, "generate_content", fake_generate)

    result = _say(client, auth, room_id, "내일까지 견적서 보낼게요")

    assert len(calls) == 1
    assert result["bot_message"]["content"] == "네, 확인했습니다."


def test_지난_대화에_방금_보낸_메시지는_들어가지_않는다(client, monkeypatch):
    """[메시지]로 따로 주는 문장이 [지난 대화]에도 있으면, 같은 문장이
    '새로 뽑을 것'과 '이미 등록된 것'에 동시에 걸린다."""
    auth, _, room_id = _setup(client)
    _say(client, auth, room_id, "/help")

    seen = {}

    def capture(recent_messages, message, **kwargs):
        seen["history"] = recent_messages
        seen["message"] = message
        return _fake_turn()

    monkeypatch.setattr(gemini_service, "chat_reply_with_actions", capture)

    _say(client, auth, room_id, "내일까지 견적서 보낼게요")

    assert seen["message"] == "내일까지 견적서 보낼게요"
    assert "내일까지 견적서 보낼게요" not in [m["content"] for m in seen["history"]]
    # 앞선 대화 자체는 남아 있어야 한다 — 겹침만 걷어내는 것이지 맥락을 버리는 게 아니다.
    assert any(m["content"] == "/help" for m in seen["history"])


def test_답변이_비면_봇_메시지를_남기지_않는다(client, monkeypatch, db_session):
    """모델이 죽어 reply가 비었을 때 빈 말풍선이 나가면 안 된다."""
    auth, _, room_id = _setup(client)
    _say(client, auth, room_id, "/help")
    before = db_session.query(ChatMessage).filter(ChatMessage.is_bot.is_(True)).count()

    monkeypatch.setattr(
        gemini_service, "chat_reply_with_actions", lambda h, m, **kw: _fake_turn(reply="")
    )

    result = _say(client, auth, room_id, "내일까지 견적서 보낼게요")

    assert result["bot_message"] is None
    after = db_session.query(ChatMessage).filter(ChatMessage.is_bot.is_(True)).count()
    assert after == before


def test_병합_호출은_한도_소진을_삼키지_않는다(monkeypatch):
    """429는 일시적 오류와 달리 사용량이 초기화될 때까지 계속 실패한다.
    빈 답으로 뭉개면 호출자가 둘을 구분할 수 없다."""

    def boom(**kwargs):
        raise genai_errors.ClientError(
            429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}}
        )

    monkeypatch.setattr(gemini_service.client.models, "generate_content", boom)

    with pytest.raises(gemini_service.QuotaExceeded):
        gemini_service.chat_reply_with_actions([], "아무 말", claim=lambda: True)


def test_배열이_null로_와도_빈_리스트를_지킨다(monkeypatch):
    """모델이 배열 자리에 null을 주면 _apply_extracted_actions의 for가
    TypeError로 터진다. ai_mode 메시지마다 도는 경로라 그대로 500이 된다."""
    monkeypatch.setattr(
        gemini_service.client.models,
        "generate_content",
        lambda **kw: _turn_response(add_todos=None, complete_todo_hints=None),
    )

    result = gemini_service.chat_reply_with_actions([], "아무 말", claim=lambda: True)

    assert result["add_todos"] == []
    assert result["complete_todo_hints"] == []


def test_문서_명령은_초안에_분류가_있으면_모델을_다시_부르지_않는다(client, monkeypatch):
    """초안 응답 스키마(_SUMMARY_SCHEMA)에 category가 이미 들어 있다.
    한 번 더 묻는 건 하루 20건짜리 한도에서 순수 낭비다."""
    auth, _, room_id = _setup(client)
    _say(client, auth, room_id, "/help")

    structured = {
        "headline": "출시일 확정",
        "key_points": ["8월 30일 출시"],
        "requests": [],
        "action_items": [],
        "notes": "",
        "commitments": [],
        "category": "기획",
    }
    monkeypatch.setattr(
        gemini_service, "draft_document_from_conversation", lambda msgs, title, **kw: structured
    )

    def must_not_be_called(text, **kwargs):
        raise AssertionError("초안에 분류가 있는데 classify_document_category를 불렀다")

    monkeypatch.setattr(gemini_service, "classify_document_category", must_not_be_called)

    result = _say(client, auth, room_id, "/문서 회의록")
    assert "회의록" in result["bot_message"]["content"]


def test_문서_명령은_초안에_분류가_없을_때만_분류를_부른다(client, monkeypatch):
    auth, _, room_id = _setup(client)
    _say(client, auth, room_id, "/help")

    structured = {
        "headline": "출시일 확정",
        "key_points": ["8월 30일 출시"],
        "requests": [],
        "action_items": [],
        "notes": "",
        "commitments": [],
        "category": "",
    }
    monkeypatch.setattr(
        gemini_service, "draft_document_from_conversation", lambda msgs, title, **kw: structured
    )
    called = []
    monkeypatch.setattr(
        gemini_service,
        "classify_document_category",
        lambda text, **kw: called.append(text) or "기타",
    )

    result = _say(client, auth, room_id, "/문서 회의록")
    assert "회의록" in result["bot_message"]["content"]
    assert len(called) == 1
