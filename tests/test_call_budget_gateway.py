"""게이트웨이가 실제로 강제되는지 검사한다.

TS-035는 korean_date_context()를 호출부 여섯 곳 중 둘에 빠뜨린 사건이었다.
테스트 265개가 전부 초록인데 마감일이 799일 어긋나 있었다 — 빠뜨려도 조용히
돌아갔기 때문이다. 예산에서 같은 일이 벌어지면 조용히 한도를 넘는다.

그래서 "빠뜨릴 수 없음"을 사람의 주의가 아니라 테스트로 잡는다.
"""

import inspect

import pytest

import gemini_service

# Gemini를 실제로 부르는 공개 함수. 새 함수를 추가하면 여기에도 넣어야 한다.
GEMINI_CALLERS = [
    "extract_chat_commitments",
    "summarize_upload",
    "classify_document_category",
    "extract_chat_actions",
    "chat_reply_with_actions",
    "summarize_conversation",
    "draft_document_from_conversation",
    "generate_bot_reply",
    "answer_assistant",
]


@pytest.mark.parametrize("name", GEMINI_CALLERS)
def test_모든_호출_함수가_claim을_필수로_받는다(name):
    fn = getattr(gemini_service, name)
    params = inspect.signature(fn).parameters

    assert "claim" in params, f"{name}이 claim을 안 받는다 — 예산 밖에서 호출이 나간다"
    assert params["claim"].default is inspect.Parameter.empty, (
        f"{name}의 claim에 기본값이 있다. 빠뜨려도 조용히 돌아가면 강제가 아니다"
    )
    assert params["claim"].kind is inspect.Parameter.KEYWORD_ONLY, (
        f"{name}의 claim이 키워드 전용이 아니다 — 위치 인자로 밀려 들어갈 수 있다"
    )


def test_목록이_실제_호출_함수를_빠짐없이_담았는가():
    """generate_content를 부르는데 GEMINI_CALLERS에 없는 함수를 잡는다.
    목록 자체가 낡는 것을 막는 안전장치다."""
    listed = set(GEMINI_CALLERS)

    for name, fn in inspect.getmembers(gemini_service, inspect.isfunction):
        if name.startswith("_") or fn.__module__ != gemini_service.__name__:
            continue
        if "generate_content" in inspect.getsource(fn) and name not in listed:
            pytest.fail(f"{name}이 generate_content를 부르는데 GEMINI_CALLERS에 없다")


def test_claim이_False면_호출하지_않고_QuotaExceeded를_올린다(monkeypatch):
    def must_not_be_called(**kwargs):
        raise AssertionError("예산이 없는데 Gemini를 불렀다")

    monkeypatch.setattr(gemini_service.client.models, "generate_content", must_not_be_called)

    with pytest.raises(gemini_service.QuotaExceeded):
        gemini_service.generate_bot_reply([], "질문", claim=lambda: False)


def test_claim이_True면_정상_호출된다(monkeypatch):
    class FakeResponse:
        text = "네, 확인했습니다."

    monkeypatch.setattr(
        gemini_service.client.models, "generate_content", lambda **kw: FakeResponse()
    )

    result = gemini_service.generate_bot_reply([], "질문", claim=lambda: True)
    assert result == "네, 확인했습니다."


def test_claim은_호출당_한_번만_불린다(monkeypatch):
    """한 함수가 claim을 두 번 부르면 장부가 실제보다 빨리 준다."""

    class FakeResponse:
        text = "네."

    monkeypatch.setattr(
        gemini_service.client.models, "generate_content", lambda **kw: FakeResponse()
    )
    calls = []
    gemini_service.generate_bot_reply([], "질문", claim=lambda: calls.append(1) or True)
    assert len(calls) == 1


def test_QuotaExceeded는_함수_내부_except에_먹히지_않는다(monkeypatch):
    """_spend를 try 안에 두면 각 함수의 except Exception이 잡아
    None이나 빈 결과로 뭉갠다. 그러면 소진이 '모델 실패'로 보인다."""

    monkeypatch.setattr(
        gemini_service.client.models,
        "generate_content",
        lambda **kw: (_ for _ in ()).throw(AssertionError("불리면 안 된다")),
    )

    with pytest.raises(gemini_service.QuotaExceeded):
        gemini_service.extract_chat_actions("아무 말", claim=lambda: False)
