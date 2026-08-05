import json
import os
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from fastapi import HTTPException, UploadFile
from google import genai
from google.genai import types

from models import DOCUMENT_CATEGORIES

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    raise RuntimeError("GOOGLE_API_KEY 환경변수가 설정되어 있지 않습니다.")

client = genai.Client(api_key=GOOGLE_API_KEY)

MODEL = "gemini-2.5-flash"


def korean_date_context() -> str:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    return f"오늘 날짜는 {now.strftime('%Y-%m-%d')}({weekdays[now.weekday()]})이다."


CALL_SUMMARY_PROMPT = """
너는 콜센터/업무 통화 요약을 전문으로 하는 비서야.
주어진 통화 녹음을 듣고 아래 JSON 스키마에 맞춰 콜 요약 리포트를 만들어 줘.

각 필드의 의미:
- headline: 통화 내용을 한두 문장으로 압축한 한 줄 요약.
- key_points: 핵심 논의 3~6개. 중요한 숫자, 날짜, 약속 사항이 있으면 함께 적는다.
- requests: 고객이나 상대방이 명확히 요청한 사항만. 없으면 빈 배열.
- action_items: 통화 후 담당자가 해야 할 일. 마감일이 언급됐으면 due_date에
  YYYY-MM-DD로, 언급되지 않았으면 빈 문자열. 급한 건은 priority를 high로.
  할 일이 없으면 빈 배열.
- notes: 톤, 분위기, 리스크, 주의사항 등 참고 메모를 1~3줄. 없으면 빈 문자열.

규칙:
- 통화와 직접 관련 없는 추측은 하지 말 것.
- 이모지, 서론, 인사말, 마크다운 기호를 쓰지 말 것.
- 모든 문자열은 한국어로 작성할 것.
"""

DOCUMENT_SUMMARY_PROMPT = """
너는 회사 업무 문서(회의록, 보고서 등)를 요약하는 비서야.
주어진 문서를 읽고 아래 JSON 스키마에 맞춰 문서 요약 리포트를 만들어 줘.

각 필드의 의미:
- headline: 문서 내용을 한두 문장으로 압축한 한 줄 요약.
- key_points: 핵심 내용 3~6개. 중요한 숫자, 날짜, 결정 사항이 있으면 함께 적는다.
- requests: 이 문서에서는 사용하지 않으므로 항상 빈 배열.
- action_items: 문서에서 확인된, 담당자가 해야 할 일. 마감일이 언급됐으면
  due_date에 YYYY-MM-DD로, 언급되지 않았으면 빈 문자열. 급한 건은 priority를
  high로. 할 일이 없으면 빈 배열.
- notes: 리스크, 주의사항 등 참고 메모를 1~3줄. 없으면 빈 문자열.

규칙:
- 문서와 직접 관련 없는 추측은 하지 말 것.
- 이모지, 서론, 인사말, 마크다운 기호를 쓰지 말 것.
- 모든 문자열은 한국어로 작성할 것.
"""

SUMMARY_PRIORITIES = ("high", "normal")

_SUMMARY_SCHEMA = {
    "type": "OBJECT",
    "required": ["headline", "key_points", "requests", "action_items", "notes"],
    "properties": {
        "headline": {"type": "STRING"},
        "key_points": {"type": "ARRAY", "items": {"type": "STRING"}},
        "requests": {"type": "ARRAY", "items": {"type": "STRING"}},
        "action_items": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "required": ["content", "due_date", "priority"],
                "properties": {
                    "content": {"type": "STRING"},
                    "due_date": {
                        "type": "STRING",
                        "description": "YYYY-MM-DD 형식. 마감일이 없으면 빈 문자열.",
                    },
                    "priority": {"type": "STRING", "enum": list(SUMMARY_PRIORITIES)},
                },
            },
        },
        "notes": {"type": "STRING"},
    },
}


def normalize_summary(raw: dict) -> dict:
    """모델 응답을 UI·DB가 신뢰할 수 있는 형태로 보정한다.

    스키마를 줘도 필드가 비거나 타입이 어긋난 채 오는 경우가 있어, 저장 전에
    한 번 걸러야 프론트에서 같은 방어 코드를 중복으로 두지 않는다.
    """

    def _clean_list(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [s.strip() for s in value if isinstance(s, str) and s.strip()]

    action_items = []
    for item in raw.get("action_items") or []:
        if not isinstance(item, dict):
            continue
        content = (item.get("content") or "").strip()
        if not content:
            continue
        priority = item.get("priority")
        action_items.append(
            {
                "content": content,
                "due_date": (item.get("due_date") or "").strip(),
                "priority": priority if priority in SUMMARY_PRIORITIES else "normal",
            }
        )

    return {
        "headline": (raw.get("headline") or "").strip(),
        "key_points": _clean_list(raw.get("key_points")),
        "requests": _clean_list(raw.get("requests")),
        "action_items": action_items,
        "notes": (raw.get("notes") or "").strip(),
    }


def render_summary_text(structured: dict) -> str:
    """구조화 요약을 평문으로 렌더한다.

    이력 검색이 요약 원문 문자열 매칭에 의존하므로, 구조화 이후에도 평문 사본을
    함께 저장한다.
    """

    blocks: list[str] = []

    if structured["headline"]:
        blocks.append(f"[한 줄 요약]\n{structured['headline']}")

    for title, items in (
        ("주요 내용", structured["key_points"]),
        ("요구사항", structured["requests"]),
    ):
        if items:
            body = "\n".join(f"- {item}" for item in items)
            blocks.append(f"[{title}]\n{body}")

    if structured["action_items"]:
        lines = []
        for item in structured["action_items"]:
            prefix = "- (우선) " if item["priority"] == "high" else "- "
            due = f" (마감 {item['due_date']})" if item["due_date"] else ""
            lines.append(f"{prefix}{item['content']}{due}")
        blocks.append("[액션 아이템]\n" + "\n".join(lines))

    if structured["notes"]:
        blocks.append(f"[메모]\n{structured['notes']}")

    return "\n\n".join(blocks)


async def summarize_upload(file: UploadFile, prompt: str) -> tuple[dict | None, str]:
    """업로드 파일을 요약해 (구조화 요약, 평문 요약)을 반환한다.

    구조화 응답을 파싱하지 못하면 스키마 없이 한 번 더 호출해 평문만 확보한다.
    오디오 입력에 스키마를 함께 거는 조합은 실패할 여지가 있어, 요약 자체를 잃는
    것보다 구조만 포기하는 편이 낫다.
    """

    try:
        suffix = os.path.splitext(file.filename or "")[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            temp_path = tmp.name
            content = await file.read()
            tmp.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 저장 중 오류: {e}")

    try:
        uploaded_file = client.files.upload(file=temp_path)

        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=[uploaded_file, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=_SUMMARY_SCHEMA,
                ),
            )
            structured = normalize_summary(json.loads(response.text))
            if structured["headline"] or structured["key_points"]:
                return structured, render_summary_text(structured)
        except Exception:
            pass

        response = client.models.generate_content(
            model=MODEL,
            contents=[uploaded_file, prompt],
        )
        summary_text = (getattr(response, "text", "") or "").strip()

        if not summary_text:
            raise HTTPException(status_code=500, detail="Gemini 요약 결과가 비어 있습니다.")

        return None, summary_text

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini 요약 중 오류: {e}")

    finally:
        try:
            os.remove(temp_path)
        except Exception:
            pass


_CLASSIFIABLE_CATEGORIES = tuple(c for c in DOCUMENT_CATEGORIES if c != "통화")

_CATEGORY_SCHEMA = {
    "type": "OBJECT",
    "required": ["category"],
    "properties": {
        "category": {"type": "STRING", "enum": list(_CLASSIFIABLE_CATEGORIES)},
    },
}


def classify_document_category(summary_text: str) -> str:
    """문서 요약 내용을 기획/디자인/개발/마케팅/기타 중 하나로 분류한다."""

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=(
                "다음은 회사 업무 문서를 요약한 내용이다. 이 문서를 "
                f"{list(_CLASSIFIABLE_CATEGORIES)} 중 하나로 분류해라.\n\n{summary_text}"
            ),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_CATEGORY_SCHEMA,
            ),
        )
        data = json.loads(response.text)
        category = data.get("category")
        if category in _CLASSIFIABLE_CATEGORIES:
            return category
    except Exception:
        pass
    return "기타"


_EMPTY_EXTRACTION = {
    "add_todos": [],
    "complete_todo_hints": [],
    "delete_todo_hints": [],
    "add_schedules": [],
    "delete_schedule_hints": [],
}

_EXTRACTION_SCHEMA = {
    "type": "OBJECT",
    "required": [
        "add_todos",
        "complete_todo_hints",
        "delete_todo_hints",
        "add_schedules",
        "delete_schedule_hints",
    ],
    "properties": {
        "add_todos": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "required": ["content", "due_date"],
                "properties": {
                    "content": {"type": "STRING"},
                    "due_date": {
                        "type": "STRING",
                        "description": "YYYY-MM-DD 형식. 마감일이 없으면 빈 문자열.",
                    },
                },
            },
        },
        "complete_todo_hints": {"type": "ARRAY", "items": {"type": "STRING"}},
        "delete_todo_hints": {"type": "ARRAY", "items": {"type": "STRING"}},
        "add_schedules": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "required": ["title", "date"],
                "properties": {
                    "title": {"type": "STRING"},
                    "date": {"type": "STRING", "description": "YYYY-MM-DD 형식."},
                },
            },
        },
        "delete_schedule_hints": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
}

_EXTRACTION_SYSTEM_PROMPT = """
너는 스타트업 팀 채팅을 지켜보는 AI PM 비서 '@비서'다.
아래 [메시지]를 분석해서, 할 일(todo)과 일정(schedule) 변경사항을 JSON으로 추출해라.

규칙:
- 명확한 업무 지시, 약속, 마감일 언급만 추출한다. 잡담·인사·질문만 있는 경우는 무시한다.
- 이미 존재할 법한 할 일/일정을 완료·취소했다는 언급이면 해당 hint 배열에 핵심 키워드만 짧게 넣는다.
- 날짜는 반드시 위에 주어진 오늘 날짜를 기준으로 YYYY-MM-DD 절대 날짜로 변환한다.
- 추출할 내용이 없으면 모든 배열을 빈 배열로 둔다.
"""


def extract_chat_actions(message: str) -> dict:
    """채팅 메시지에서 할 일/일정 변경사항을 구조화된 JSON으로 추출한다."""

    prompt = f"{korean_date_context()}\n\n{_EXTRACTION_SYSTEM_PROMPT}\n\n[메시지]\n{message}"

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_EXTRACTION_SCHEMA,
            ),
        )
        data = json.loads(response.text)
        return {**_EMPTY_EXTRACTION, **data}
    except Exception:
        return dict(_EMPTY_EXTRACTION)


_BOT_PERSONA_PROMPT = """
너는 스타트업의 업무 흐름을 꿰뚫는 꼼꼼한 PM 비서 '@비서'다.
동료들의 업무를 돕고, 대화 맥락을 이해해 적절한 피드백을 준다.
답변은 2~4문장 이내로 짧고 친근하게, 한국어 존댓말로 한다.
"""


def generate_bot_reply(recent_messages: list[dict], new_message: str) -> str:
    """@비서 멘션에 대한 AI PM 봇 답변을 생성한다."""

    history_text = "\n".join(f"{m['sender']}: {m['content']}" for m in recent_messages)
    prompt = (
        f"{korean_date_context()}\n\n{_BOT_PERSONA_PROMPT}\n\n"
        f"[최근 대화]\n{history_text}\n\n[새 메시지]\n{new_message}\n\n"
        "@비서로서 위 새 메시지에 답변해줘."
    )

    try:
        response = client.models.generate_content(model=MODEL, contents=prompt)
        return getattr(response, "text", "").strip() or "네, 확인했습니다."
    except Exception:
        return "죄송해요, 지금은 답변을 생성하지 못했어요."
