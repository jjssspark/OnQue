import gemini_service


SAMPLE_STRUCTURED = {
    "headline": "9월 출시 일정을 확정했다.",
    "key_points": ["베타는 8월 20일 오픈", "가격 정책은 다음 회의로 미룸"],
    "requests": ["데모 계정을 미리 달라"],
    "action_items": [
        {"content": "베타 안내 메일 발송", "due_date": "2026-08-18", "priority": "high"},
        {"content": "가격표 초안 작성", "due_date": "", "priority": "normal"},
    ],
    "notes": "상대방이 일정에 민감함.",
}


def _setup_group(client):
    token = client.post(
        "/api/v1/auth/signup",
        json={"email": "admin@onque.dev", "password": "password123", "name": "관리자"},
    ).json()["data"]["token"]
    group_id = client.post(
        "/api/v1/groups", json={"name": "A팀"}, headers={"Authorization": f"Bearer {token}"}
    ).json()["data"]["id"]
    return token, group_id


def _stub_gemini(monkeypatch, structured):
    async def fake_summarize(file, prompt):
        text = gemini_service.render_summary_text(structured) if structured else "평문 요약"
        return structured, text

    monkeypatch.setattr(gemini_service, "summarize_upload", fake_summarize)
    monkeypatch.setattr(gemini_service, "classify_document_category", lambda text: "기획")


# ── 요약 정규화/렌더 ──────────────────────────────────────────


def test_normalize_summary_drops_empty_and_malformed_entries():
    result = gemini_service.normalize_summary(
        {
            "headline": "  제목  ",
            "key_points": ["  유효  ", "", 42],
            "requests": "리스트가 아님",
            "action_items": [
                {"content": "  할 일  ", "due_date": " 2026-08-18 ", "priority": "urgent"},
                {"content": "   "},
                "객체가 아님",
            ],
            "notes": None,
        }
    )

    assert result == {
        "headline": "제목",
        "key_points": ["유효"],
        "requests": [],
        "action_items": [
            {"content": "할 일", "due_date": "2026-08-18", "priority": "normal"}
        ],
        "notes": "",
    }


def test_render_summary_text_omits_empty_sections_and_marks_priority():
    text = gemini_service.render_summary_text(SAMPLE_STRUCTURED)

    assert "[한 줄 요약]" in text
    assert "[요구사항]" in text
    assert "- (우선) 베타 안내 메일 발송 (마감 2026-08-18)" in text
    assert "- 가격표 초안 작성" in text
    assert "(마감 )" not in text


def test_render_summary_text_skips_sections_without_content():
    text = gemini_service.render_summary_text(
        gemini_service.normalize_summary({"headline": "한 줄만 있음"})
    )

    assert text == "[한 줄 요약]\n한 줄만 있음"


# ── 요약 엔드포인트 ──────────────────────────────────────────


def test_summarize_document_stores_structured_summary(client, monkeypatch):
    token, group_id = _setup_group(client)
    _stub_gemini(monkeypatch, SAMPLE_STRUCTURED)

    res = client.post(
        "/summarize-document",
        params={"group_id": group_id},
        files={"file": ("meeting.txt", b"content", "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["structured"]["headline"] == SAMPLE_STRUCTURED["headline"]
    assert body["created_todos"] == []

    listed = client.get(
        "/documents", params={"group_id": group_id}, headers={"Authorization": f"Bearer {token}"}
    ).json()
    assert listed[0]["structured"]["action_items"][0]["content"] == "베타 안내 메일 발송"


def test_summarize_document_auto_todo_creates_todos(client, monkeypatch):
    token, group_id = _setup_group(client)
    _stub_gemini(monkeypatch, SAMPLE_STRUCTURED)

    res = client.post(
        "/summarize-document",
        params={"group_id": group_id, "auto_todo": True},
        files={"file": ("meeting.txt", b"content", "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )

    created = res.json()["created_todos"]
    assert [t["content"] for t in created] == ["베타 안내 메일 발송", "가격표 초안 작성"]
    assert created[0]["due_date"] == "2026-08-18"
    assert created[1]["due_date"] is None

    todos = client.get(
        "/todos", params={"group_id": group_id}, headers={"Authorization": f"Bearer {token}"}
    ).json()
    assert len(todos) == 2


def test_summarize_document_falls_back_to_plain_text(client, monkeypatch):
    token, group_id = _setup_group(client)
    _stub_gemini(monkeypatch, None)

    res = client.post(
        "/summarize-document",
        params={"group_id": group_id, "auto_todo": True},
        files={"file": ("meeting.txt", b"content", "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )

    body = res.json()
    assert body["structured"] is None
    assert body["summary"] == "평문 요약"
    # 구조가 없으면 등록할 액션 아이템도 없다.
    assert body["created_todos"] == []

    listed = client.get(
        "/documents", params={"group_id": group_id}, headers={"Authorization": f"Bearer {token}"}
    ).json()
    assert listed[0]["structured"] is None


# ── 수동 할 일 등록 ──────────────────────────────────────────


def test_create_todo_registers_action_item(client):
    token, group_id = _setup_group(client)

    res = client.post(
        "/todos",
        json={"group_id": group_id, "content": "가격표 초안 작성", "due_date": "2026-08-20"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert res.status_code == 200
    assert res.json()["content"] == "가격표 초안 작성"
    assert res.json()["due_date"] == "2026-08-20"
    assert res.json()["is_done"] is False


def test_create_todo_rejects_blank_content(client):
    token, group_id = _setup_group(client)

    res = client.post(
        "/todos",
        json={"group_id": group_id, "content": "   "},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert res.status_code == 400
    assert res.json()["error"]["code"] == "TODO_CONTENT_REQUIRED"


def test_create_todo_rejects_non_member(client):
    _, group_id = _setup_group(client)
    other_token = client.post(
        "/api/v1/auth/signup",
        json={"email": "other@onque.dev", "password": "password123", "name": "타인"},
    ).json()["data"]["token"]

    res = client.post(
        "/todos",
        json={"group_id": group_id, "content": "남의 그룹 할 일"},
        headers={"Authorization": f"Bearer {other_token}"},
    )

    assert res.status_code == 403
    assert res.json()["error"]["code"] == "GROUP_ACCESS_FORBIDDEN"
