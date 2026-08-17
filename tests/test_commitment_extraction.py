import json
import logging
from datetime import date, datetime, timezone

import commitment_service
import gemini_service
from gemini_service import extract_chat_commitments, normalize_summary
from models import Client, Commitment


def test_normalize_summary_extracts_commitments():
    raw = {
        "headline": "A사 킥오프",
        "key_points": [],
        "requests": [],
        "action_items": [],
        "notes": "",
        "commitments": [
            {
                "content": "시안 3종 전달",
                "client_name": "A사",
                "due_date": "2026-08-13",
                "evidence": "수요일까지 시안 세 개 보내드릴게요",
            }
        ],
    }
    result = normalize_summary(raw)
    assert result["commitments"] == [
        {
            "content": "시안 3종 전달",
            "client_name": "A사",
            "due_date": "2026-08-13",
            "evidence": "수요일까지 시안 세 개 보내드릴게요",
        }
    ]


def test_normalize_summary_defaults_commitments_to_empty():
    raw = {"headline": "회의", "key_points": [], "requests": [], "action_items": [], "notes": ""}
    assert normalize_summary(raw)["commitments"] == []


def test_normalize_summary_drops_commitment_without_evidence():
    """근거 없는 약속은 사람이 판단할 수 없으므로 버린다."""
    raw = {
        "headline": "",
        "key_points": [],
        "requests": [],
        "action_items": [],
        "notes": "",
        "commitments": [
            {"content": "뭔가 하기", "client_name": "", "due_date": "", "evidence": ""},
            {"content": "", "client_name": "A사", "due_date": "", "evidence": "근거만 있음"},
        ],
    }
    assert normalize_summary(raw)["commitments"] == []


def test_normalize_summary_handles_non_list_commitments_as_scalar():
    """모델이 commitments를 리스트가 아닌 값으로 뱉어도 예외 없이 빈 리스트가 된다."""
    raw = {
        "headline": "",
        "key_points": [],
        "requests": [],
        "action_items": [],
        "notes": "",
        "commitments": 42,
    }
    assert normalize_summary(raw)["commitments"] == []


def test_normalize_summary_handles_non_list_commitments_as_string():
    raw = {
        "headline": "",
        "key_points": [],
        "requests": [],
        "action_items": [],
        "notes": "",
        "commitments": "약속 없음",
    }
    assert normalize_summary(raw)["commitments"] == []


def test_resolve_client_id_matches_existing(client, db_session):
    a = Client(group_id=1, name="A사")
    db_session.add(a)
    db_session.commit()

    assert commitment_service.resolve_client_id(db_session, 1, "A사") == a.id
    assert commitment_service.resolve_client_id(db_session, 1, " A사 ") == a.id


def test_resolve_client_id_returns_none_and_creates_nothing(client, db_session):
    """모델이 언급했다는 이유로 Client를 만들지 않는다 — 환각이 목록을 오염시킨다."""
    assert commitment_service.resolve_client_id(db_session, 1, "듣보사") is None
    assert db_session.query(Client).count() == 0


def test_resolve_client_id_does_not_cross_groups(client, db_session):
    db_session.add(Client(group_id=2, name="A사"))
    db_session.commit()

    assert commitment_service.resolve_client_id(db_session, 1, "A사") is None


def test_create_commitments_stores_proposed(client, db_session):
    a = Client(group_id=1, name="A사")
    db_session.add(a)
    db_session.commit()

    created = commitment_service.create_commitments(
        db_session,
        group_id=1,
        items=[
            {
                "content": "시안 3종 전달",
                "client_name": "A사",
                "due_date": "2026-08-13",
                "evidence": "수요일까지 드릴게요",
            },
            {
                "content": "견적서 발송",
                "client_name": "듣보사",
                "due_date": "",
                "evidence": "견적은 내일 드릴게요",
            },
        ],
        source_type="call",
        source_id=7,
    )
    db_session.commit()

    assert len(created) == 2
    assert created[0].status == "proposed"
    assert created[0].client_id == a.id
    assert created[0].due_date == date(2026, 8, 13)
    assert created[0].source_type == "call"
    assert created[0].source_id == 7
    # 이름을 못 찾은 쪽은 client_id 없이 저장된다
    assert created[1].client_id is None
    assert created[1].due_date is None


def test_create_commitments_with_empty_list(client, db_session):
    assert commitment_service.create_commitments(
        db_session, group_id=1, items=[], source_type="chat", source_id=None, room_id=1
    ) == []
    assert db_session.query(Commitment).count() == 0


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text


def test_extract_chat_commitments_shares_normalize_summary_guard(monkeypatch):
    """모델이 commitments를 리스트가 아닌 값("없음")으로 뱉어도 예외 없이
    빈 리스트를 돌려줘야 한다. normalize_summary와 같은 가드를 공유하는지
    검증한다 — 공유하지 않으면 채팅 경로는 create_commitments에서 문자열을
    순회하다 그대로 죽고, 실패 시 스캔 포인터가 멈추므로 같은 배치를
    영원히 재시도하게 된다."""
    monkeypatch.setattr(
        gemini_service.client.models,
        "generate_content",
        lambda **kwargs: _FakeResponse(json.dumps({"commitments": "약속 없음"})),
    )
    assert extract_chat_commitments("아무 대화", claim=lambda: True) == []


def test_extract_chat_commitments_logs_warning_on_failure(monkeypatch, caplog):
    """실패 원인이 로그 없이 사라지면 안 된다 — observability.md 요구사항."""

    def boom(**kwargs):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(gemini_service.client.models, "generate_content", boom)

    with caplog.at_level(logging.WARNING, logger="gemini_service"):
        result = extract_chat_commitments("아무 대화", claim=lambda: True)

    assert result is None
    records = [r for r in caplog.records if r.name == "gemini_service"]
    assert len(records) == 1
    assert records[0].event == "commitment.chat_extraction.failed"
    assert records[0].exc_info is not None


def test_today_kst_reports_seoul_date_not_utc_date(monkeypatch):
    """UTC 23:30이면 KST는 이미 다음날 08:30이다. 서버가 UTC로 돌아도
    기한 판정은 KST 기준이어야 자정~09시 사이에 어제 넘긴 기한이
    '오늘 마감'으로 잘못 보이지 않는다."""

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            utc_instant = datetime(2026, 1, 1, 23, 30, tzinfo=timezone.utc)
            return utc_instant.astimezone(tz) if tz else utc_instant

    monkeypatch.setattr(commitment_service, "datetime", FixedDatetime)
    assert commitment_service.today_kst() == date(2026, 1, 2)


def test_summary_survives_commitment_failure(client, db_session, monkeypatch):
    """약속 저장이 터져도 요약 문서는 남아야 한다."""
    import main
    from models import Document

    token = client.post(
        "/api/v1/auth/signup",
        json={"email": "admin@onque.dev", "password": "password123", "name": "관리자"},
    ).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    group = client.post("/api/v1/groups", json={"name": "A팀"}, headers=headers).json()["data"]

    async def fake_summarize(file, prompt, **kwargs):
        return (
            {
                "headline": "요약됨",
                "key_points": [],
                "requests": [],
                "action_items": [],
                "notes": "",
                "commitments": [
                    {"content": "시안 전달", "client_name": "", "due_date": "", "evidence": "드릴게요"}
                ],
            },
            "요약됨",
        )

    def boom(*args, **kwargs):
        raise RuntimeError("DB 폭발")

    monkeypatch.setattr(main.gemini_service, "summarize_upload", fake_summarize)
    monkeypatch.setattr(main.gemini_service, "classify_document_category", lambda t, **kw: "기타")
    monkeypatch.setattr(main.commitment_service, "create_commitments", boom)

    res = client.post(
        "/summarize-document",
        params={"group_id": group["id"]},
        files={"file": ("test.txt", b"content", "text/plain")},
        headers=headers,
    )

    assert res.status_code == 200
    assert db_session.query(Document).count() == 1
