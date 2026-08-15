import asyncio
import io
import json
from types import SimpleNamespace

import pytest
from fastapi import UploadFile
from google.genai import errors as genai_errors

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


def test_normalize_summary_keeps_valid_category_and_rejects_unknown():
    """분류가 요약 응답에 합쳐졌으므로, 모델이 지어낸 값이 그대로 DB에 들어가면
    안 된다. 허용 목록에 있는 값만 통과시키고 나머지는 기타로 떨어뜨린다."""
    valid = gemini_service._CLASSIFIABLE_CATEGORIES[0]

    assert gemini_service.normalize_summary({"category": valid})["category"] == valid
    assert gemini_service.normalize_summary({"category": "없는분류"})["category"] == "기타"
    # 통화는 분류 대상에서 빠져 있다. 라우터가 명시적으로 넘기는 값이라
    # 모델이 고를 수 있으면 안 된다.
    assert gemini_service.normalize_summary({"category": "통화"})["category"] == "기타"


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
        # 분류가 요약 응답에 합쳐졌다. 위 입력에 category가 없으므로 기본값이
        # 나와야 한다 — 모델이 필드를 빠뜨려도 저장이 깨지면 안 된다.
        "category": "기타",
        "headline": "제목",
        "key_points": ["유효"],
        "requests": [],
        "action_items": [
            {"content": "할 일", "due_date": "2026-08-18", "priority": "normal"}
        ],
        "notes": "",
        "commitments": [],
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


# ── 한도 소진 ────────────────────────────────────────────────


def _quota_error():
    return genai_errors.ClientError(
        429,
        {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}},
    )


def test_summarize_stops_on_quota_instead_of_retrying(monkeypatch):
    """요약은 1차가 실패하면 File API로 바꿔 재시도한다. 한도 소진일 때 그
    재시도는 성공할 수 없으면서 호출만 더 먹는다 — 재시도 전에 끊어야 한다."""
    calls = []

    def boom(**kwargs):
        calls.append(1)
        raise _quota_error()

    def no_upload(**kwargs):
        raise AssertionError("한도 소진 뒤 File API 업로드를 시도하면 안 된다")

    monkeypatch.setattr(gemini_service.client.models, "generate_content", boom)
    monkeypatch.setattr(gemini_service.client.files, "upload", no_upload)

    upload = UploadFile(file=io.BytesIO("회의록 내용".encode()), filename="meeting.txt")

    with pytest.raises(gemini_service.QuotaExceeded):
        asyncio.run(gemini_service.summarize_upload(upload, "요약해라"))

    assert len(calls) == 1


def test_summarize_still_falls_back_on_other_errors(monkeypatch):
    """한도만 구분한다. 나머지 실패는 종전대로 폴백 호출로 넘어가야 한다."""
    calls = []

    def flaky(**kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("구조화 파싱 실패")
        return SimpleNamespace(text="평문 요약")

    monkeypatch.setattr(gemini_service.client.models, "generate_content", flaky)
    # 폴백은 인라인이 원인일 수 있다고 보고 File API로 바꿔 다시 올린다.
    # 막지 않으면 이 테스트가 실제 네트워크를 탄다.
    monkeypatch.setattr(
        gemini_service.client.files, "upload", lambda **kwargs: SimpleNamespace(name="files/x")
    )

    upload = UploadFile(file=io.BytesIO("회의록 내용".encode()), filename="meeting.txt")
    structured, text = asyncio.run(gemini_service.summarize_upload(upload, "요약해라"))

    assert structured is None
    assert text == "평문 요약"
    assert len(calls) == 2


def test_summarize_endpoint_returns_429_with_its_own_code(client, monkeypatch):
    """500으로 뭉개면 사용자는 파일이 잘못된 줄 알고 다른 파일로 재시도한다.
    그 재시도도 전부 실패한다."""
    token, group_id = _setup_group(client)

    async def boom(file, prompt):
        raise gemini_service.QuotaExceeded()

    monkeypatch.setattr(gemini_service, "summarize_upload", boom)

    res = client.post(
        "/summarize-document",
        params={"group_id": group_id},
        files={"file": ("meeting.txt", b"content", "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert res.status_code == 429
    assert res.json()["error"]["code"] == "DOCUMENT_QUOTA_EXCEEDED"


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


# ── 업로드 요약 프롬프트의 날짜 기준 ──────────────────────────


def _capture_upload_prompt(monkeypatch, *, structured=SAMPLE_STRUCTURED):
    """summarize_upload가 모델에 실제로 보낸 프롬프트를 잡아둔다."""

    seen: dict = {}

    def fake_generate(model, contents, config=None):
        seen["contents"] = contents
        return SimpleNamespace(text=json.dumps(structured, ensure_ascii=False))

    monkeypatch.setattr(gemini_service.client.models, "generate_content", fake_generate)
    return seen


def test_통화_요약_프롬프트에_오늘_날짜가_들어간다(monkeypatch):
    """모델이 '이번 주 금요일'을 절대 날짜로 바꾸려면 오늘이 언제인지 알아야 한다.

    실측: 이 줄이 없을 때 2026-08-15에 올린 통화의 마감이 2024-06-07로 나왔다.
    학습 데이터 시점을 짚은 것으로, 799일 지난 할 일이 대시보드 맨 위에 떴다.
    """
    seen = _capture_upload_prompt(monkeypatch)
    upload = UploadFile(filename="통화.wav", file=io.BytesIO(b"fake audio"))

    asyncio.run(gemini_service.summarize_upload(upload, gemini_service.CALL_SUMMARY_PROMPT))

    assert gemini_service.korean_date_context() in seen["contents"][-1]


def test_문서_요약_프롬프트에_오늘_날짜가_들어간다(monkeypatch):
    """문서 업로드도 같은 경로를 탄다. 통화만 고치면 절반만 고친 것이다."""
    seen = _capture_upload_prompt(monkeypatch)
    upload = UploadFile(filename="회의록.txt", file=io.BytesIO(b"fake text"))

    asyncio.run(gemini_service.summarize_upload(upload, gemini_service.DOCUMENT_SUMMARY_PROMPT))

    assert gemini_service.korean_date_context() in seen["contents"][-1]


def test_날짜를_붙여도_원래_지시가_남는다(monkeypatch):
    """날짜만 남기고 프롬프트를 덮어쓰면 요약 규격이 통째로 사라진다."""
    seen = _capture_upload_prompt(monkeypatch)
    upload = UploadFile(filename="통화.wav", file=io.BytesIO(b"fake audio"))

    asyncio.run(gemini_service.summarize_upload(upload, gemini_service.CALL_SUMMARY_PROMPT))

    assert gemini_service.CALL_SUMMARY_PROMPT in seen["contents"][-1]
