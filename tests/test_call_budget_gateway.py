"""게이트웨이가 실제로 강제되는지 검사한다.

TS-035는 korean_date_context()를 호출부 여섯 곳 중 둘에 빠뜨린 사건이었다.
테스트 265개가 전부 초록인데 마감일이 799일 어긋나 있었다 — 빠뜨려도 조용히
돌아갔기 때문이다. 예산에서 같은 일이 벌어지면 조용히 한도를 넘는다.

그래서 "빠뜨릴 수 없음"을 사람의 주의가 아니라 테스트로 잡는다.
"""

import ast
import asyncio
import inspect
import io
import pathlib
import textwrap

import pytest
from fastapi import UploadFile

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


def _reachable_source(fn) -> str:
    """함수 자기 소스 + 그 함수가 부르는 모듈 내 함수들의 소스를 전이적으로 모은다.

    자기 소스만 보면 헬퍼를 경유하는 함수를 놓친다. `def summarize_audio(...):
    return _call_model(...)` 같은 모양은 리팩터링 한 번이면 자연스럽게 생기고,
    그때 새 함수는 claim 없이 검사를 통과한다. _as_content_part가 이미 그런
    모듈 내부 헬퍼다.
    """
    collected: list[str] = []
    seen: set[str] = set()
    pending = [fn]

    while pending:
        current = pending.pop()
        if current.__name__ in seen:
            continue
        seen.add(current.__name__)

        source = inspect.getsource(current)
        collected.append(source)

        for node in ast.walk(ast.parse(textwrap.dedent(source))):
            if not isinstance(node, ast.Name):
                continue
            target = getattr(gemini_service, node.id, None)
            if inspect.isfunction(target) and target.__module__ == gemini_service.__name__:
                pending.append(target)

    return "\n".join(collected)


def test_목록이_실제_호출_함수를_빠짐없이_담았는가():
    """generate_content에 (직접이든 헬퍼를 거쳐서든) 닿는데 GEMINI_CALLERS에
    없는 함수를 잡는다. 목록 자체가 낡는 것을 막는 안전장치다."""
    listed = set(GEMINI_CALLERS)

    for name, fn in inspect.getmembers(gemini_service, inspect.isfunction):
        if name.startswith("_") or fn.__module__ != gemini_service.__name__:
            continue
        if "generate_content" in _reachable_source(fn) and name not in listed:
            pytest.fail(f"{name}이 generate_content에 닿는데 GEMINI_CALLERS에 없다")


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


def test_모델_호출이_한_번이면_claim도_한_번이다(monkeypatch):
    """불변조건은 '함수당 1회'가 아니라 '나가는 모델 호출당 1회'다.

    한 호출에 claim을 두 번 부르면 장부가 실제보다 빨리 준다. 반대로 호출이
    두 번 나가는 경로(summarize_upload의 폴백)는 선점도 두 번 해야 한다 —
    그쪽은 tests/test_summary_routes.py가 지킨다. 이 테스트를 '함수당 1회'로
    읽고 폴백의 두 번째 선점을 지우면 안 된다.
    """

    class FakeResponse:
        text = "네."

    monkeypatch.setattr(
        gemini_service.client.models, "generate_content", lambda **kw: FakeResponse()
    )
    calls = []
    gemini_service.generate_bot_reply([], "질문", claim=lambda: calls.append(1) or True)
    assert len(calls) == 1


def _dummy_upload() -> UploadFile:
    return UploadFile(file=io.BytesIO("회의록 내용".encode()), filename="meeting.txt")


_MESSAGES = [{"sender": "김담당", "content": "내일까지 시안 드릴게요"}]

# 9개 함수를 각자의 최소 인자로 부르는 법. GEMINI_CALLERS에 함수를 추가하면
# 여기에도 넣어야 한다 — 안 넣으면 아래 테스트가 KeyError로 터진다.
_INVOCATIONS = {
    "extract_chat_commitments": lambda claim: gemini_service.extract_chat_commitments(
        "김담당: 내일까지 시안 드릴게요", claim=claim
    ),
    "summarize_upload": lambda claim: asyncio.run(
        gemini_service.summarize_upload(_dummy_upload(), "요약해라", claim=claim)
    ),
    "classify_document_category": lambda claim: gemini_service.classify_document_category(
        "요약 내용", claim=claim
    ),
    "extract_chat_actions": lambda claim: gemini_service.extract_chat_actions(
        "아무 말", claim=claim
    ),
    "chat_reply_with_actions": lambda claim: gemini_service.chat_reply_with_actions(
        [], "아무 말", claim=claim
    ),
    "summarize_conversation": lambda claim: gemini_service.summarize_conversation(
        _MESSAGES, claim=claim
    ),
    "draft_document_from_conversation": (
        lambda claim: gemini_service.draft_document_from_conversation(
            _MESSAGES, "회의록", claim=claim
        )
    ),
    "generate_bot_reply": lambda claim: gemini_service.generate_bot_reply(
        [], "질문", claim=claim
    ),
    "answer_assistant": lambda claim: gemini_service.answer_assistant(
        "ctx", [], "질문", claim=claim
    ),
}


@pytest.mark.parametrize("name", GEMINI_CALLERS)
def test_QuotaExceeded는_함수_내부_except에_먹히지_않는다(name, monkeypatch):
    """_spend를 try 안에 두면 각 함수의 except Exception이 잡아 None이나 빈
    결과로 뭉갠다. 그러면 소진이 '모델 실패'로 보인다.

    9개를 전부 검사하는 이유: classify_document_category는 except가
    `pass` → `return "기타"`라, _spend가 안으로 들어가면 예산 소진이 모든
    문서를 조용히 '기타'로 분류하는 것으로 둔갑하고 스위트는 초록으로 남는다.
    summarize_conversation·generate_bot_reply도 친절한 한국어 문자열로 뭉갠다.
    """
    monkeypatch.setattr(
        gemini_service.client.models,
        "generate_content",
        lambda **kw: (_ for _ in ()).throw(AssertionError("예산이 없는데 Gemini를 불렀다")),
    )
    monkeypatch.setattr(
        gemini_service.client.files,
        "upload",
        lambda **kw: (_ for _ in ()).throw(AssertionError("예산이 없는데 업로드했다")),
    )

    with pytest.raises(gemini_service.QuotaExceeded):
        _INVOCATIONS[name](lambda: False)


@pytest.mark.parametrize(
    "call",
    [
        lambda claim: gemini_service.summarize_conversation([], claim=claim),
        lambda claim: gemini_service.draft_document_from_conversation([], "회의록", claim=claim),
    ],
    ids=["summarize_conversation", "draft_document_from_conversation"],
)
def test_조기_반환은_예산을_태우지_않는다(call):
    """호출하지 않을 것에 예산을 태우면 안 된다. 조기 반환이 _spend보다
    뒤로 밀리면 빈 입력마다 한 건씩 사라진다."""
    claimed = []
    call(lambda: claimed.append(1) or True)
    assert claimed == []


# 게이트웨이를 부르는 프로덕션 모듈. 테스트는 뺀다 — 스텁을 부르지 진짜를 안 부른다.
_CALLER_MODULES = ("main.py", "commitment_service.py", "routers/assistant.py")


def _gemini_call_nodes(tree: ast.Module) -> list[tuple[str, ast.Call]]:
    """이 모듈 안에서 GEMINI_CALLERS를 부르는 ast.Call을 모은다.

    `gemini_service.foo(...)` 형태와 `from gemini_service import foo` 뒤의
    `foo(...)` 형태를 둘 다 잡는다.
    """
    imported = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "gemini_service"
        for alias in node.names
        if alias.name in GEMINI_CALLERS
    }

    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "gemini_service"
            and func.attr in GEMINI_CALLERS
        ):
            found.append((func.attr, node))
        elif isinstance(func, ast.Name) and func.id in imported:
            found.append((func.id, node))
    return found


def test_호출부가_전부_claim을_넘긴다():
    """스텁 25개에 **kwargs를 붙인 대가로, 라우트 테스트는 호출부에서 claim=을
    지워도 초록이다. '빠뜨리면 TypeError'라는 보장이 CI가 아니라 프로덕션
    런타임에서만 작동한다는 뜻이다 — 특히 구조화 파싱 실패에만 도는
    classify_document_category 폴백 두 곳은 배포 한참 뒤 500으로 드러난다.

    스텁 arity를 조이는 것보다 이 검사가 싸다.
    """
    root = pathlib.Path(__file__).resolve().parent.parent
    covered = set()

    for relative in _CALLER_MODULES:
        path = root / relative
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for name, node in _gemini_call_nodes(tree):
            covered.add(name)
            keywords = {kw.arg for kw in node.keywords}
            assert "claim" in keywords, (
                f"{relative}:{node.lineno} gemini_service.{name}() 호출에 claim=이 없다 "
                "— 예산 밖에서 호출이 나간다"
            )

    # 검사가 아무것도 못 찾고 조용히 통과하는 상태를 막는다.
    assert covered == set(GEMINI_CALLERS), (
        f"호출부를 못 찾은 함수: {sorted(set(GEMINI_CALLERS) - covered)}"
    )
