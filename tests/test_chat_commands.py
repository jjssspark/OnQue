import gemini_service
from models import Document, Todo


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


def test_plain_message_does_not_call_gemini_when_ai_is_absent(client, monkeypatch):
    auth, _, room_id = _setup(client)

    def explode(*args, **kwargs):
        raise AssertionError("AI가 없는 방에서 Gemini를 호출하면 안 된다")

    monkeypatch.setattr(gemini_service, "extract_chat_actions", explode)
    monkeypatch.setattr(gemini_service, "generate_bot_reply", explode)

    result = _say(client, auth, room_id, "점심 뭐 드실래요")

    assert result["bot_message"] is None
    assert result["ai_mode"] is False


def test_help_summons_ai_and_exit_dismisses_it(client, monkeypatch):
    auth, _, room_id = _setup(client)
    monkeypatch.setattr(gemini_service, "extract_chat_actions", lambda c: {"add_todos": []})
    monkeypatch.setattr(gemini_service, "generate_bot_reply", lambda h, m: "네, 확인했습니다.")

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
    monkeypatch.setattr(gemini_service, "summarize_conversation", lambda msgs: "출시일을 확정했다.")

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
        gemini_service, "draft_document_from_conversation", lambda msgs, title: structured
    )
    monkeypatch.setattr(gemini_service, "classify_document_category", lambda text: "기획")

    result = _say(client, auth, room_id, "/문서 8월 첫째주 회의록")

    assert "8월 첫째주 회의록" in result["bot_message"]["content"]
    doc = db_session.query(Document).one()
    assert doc.filename == "8월 첫째주 회의록"
    assert doc.source_type == "document"
    assert "9월 출시 일정을 확정했다." in doc.summary


def test_document_command_reports_when_draft_fails(client, monkeypatch):
    auth, _, room_id = _setup(client)
    monkeypatch.setattr(
        gemini_service, "draft_document_from_conversation", lambda msgs, title: None
    )

    result = _say(client, auth, room_id, "/문서")

    assert "부족" in result["bot_message"]["content"]


def test_todo_command_registers_with_parsed_due_date(client, monkeypatch):
    auth, _, room_id = _setup(client)
    monkeypatch.setattr(
        gemini_service,
        "extract_chat_actions",
        lambda c: {"add_todos": [{"content": "견적서 제출", "due_date": "2026-08-12"}]},
    )

    result = _say(client, auth, room_id, "/할일 견적서 8월 12일까지")

    assert "견적서 제출" in result["bot_message"]["content"]
    assert [(t["content"], t["due_date"]) for t in result["todos"]] == [
        ("견적서 제출", "2026-08-12")
    ]


def test_todo_command_falls_back_to_raw_text(client, monkeypatch, db_session):
    auth, _, room_id = _setup(client)
    # 추출기가 아무것도 못 뽑아도 사용자가 적은 내용은 잃지 않는다.
    monkeypatch.setattr(gemini_service, "extract_chat_actions", lambda c: {"add_todos": []})

    _say(client, auth, room_id, "/할일 사무실 비품 주문")

    assert [t.content for t in db_session.query(Todo).all()] == ["사무실 비품 주문"]


def test_todo_command_without_argument_asks_for_content(client):
    auth, _, room_id = _setup(client)

    result = _say(client, auth, room_id, "/할일")

    assert "적어주세요" in result["bot_message"]["content"]


def test_ask_command_replies_without_entering_ai_mode(client, monkeypatch):
    auth, _, room_id = _setup(client)
    monkeypatch.setattr(gemini_service, "generate_bot_reply", lambda h, m: "A안이 더 빠릅니다.")

    result = _say(client, auth, room_id, "/질문 A안과 B안 차이가 뭐야")

    assert result["bot_message"]["content"] == "A안이 더 빠릅니다."
    assert result["ai_mode"] is False


def test_unknown_command_lists_available_ones(client):
    auth, _, room_id = _setup(client)

    result = _say(client, auth, room_id, "/없는명령")

    assert "모르는 명령" in result["bot_message"]["content"]
    assert "/help" in result["bot_message"]["content"]


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
        gemini_service, "draft_document_from_conversation", lambda msgs, title: structured
    )

    def must_not_be_called(text):
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
        gemini_service, "draft_document_from_conversation", lambda msgs, title: structured
    )
    called = []
    monkeypatch.setattr(
        gemini_service,
        "classify_document_category",
        lambda text: called.append(text) or "기타",
    )

    result = _say(client, auth, room_id, "/문서 회의록")
    assert "회의록" in result["bot_message"]["content"]
    assert len(called) == 1
