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
아래 형식으로, 보기 좋고 직관적인 "콜 요약 리포트"를 만들어 줘.

형식은 꼭 아래처럼 맞춰 줘 (제목/구분선/불릿 포함):

[📌 한 줄 요약]
- 통화 내용을 한두 문장으로 요약

[💬 주요 논의 내용]
- 핵심 논의 3~6개를 불릿으로 정리
- 중요한 숫자, 날짜, 약속 사항이 있으면 함께 적기

[🙋‍♀️ 고객/상대방 요구사항]
- 고객이나 상대방이 명확히 요청한 사항만 bullet로 정리
- 요구사항이 전혀 없으면 이 [🙋‍♀️ 고객/상대방 요구사항] 섹션은 아예 출력하지 말 것

[✅ 다음 액션 아이템]
- 통화 후 담당자가 해야 할 일을 bullet로 정리
- 우선순위가 있으면 (우선) 표시
- 실행할 일이 없다면 이 [✅ 다음 액션 아이템] 섹션은 아예 출력하지 말 것

[📝 기타 메모]
- 톤, 분위기, 리스크, 주의사항 등 참고용 메모를 1~3줄 이내로 정리
- 특별히 남길 메모가 없다면 이 [📝 기타 메모] 섹션은 아예 출력하지 말 것

규칙:
- 출력은 반드시 위와 같은 섹션 제목 형식을 그대로 사용할 것.
- 불릿은 모두 "- "로 시작할 것.
- 불필요한 서론, 설명 문장, 인사말은 쓰지 말 것.
- 통화와 직접 관련 없는 추측은 하지 말 것.
- 전체 분량은 A4 1장 이내, 너무 장황하게 쓰지 말 것.

응답은 한국어로만 작성해 줘.
"""

DOCUMENT_SUMMARY_PROMPT = """
너는 회사 업무 문서(회의록, 보고서 등)를 요약하는 비서야.
아래 형식으로, 보기 좋고 직관적인 "문서 요약 리포트"를 만들어 줘.

형식은 꼭 아래처럼 맞춰 줘 (제목/구분선/불릿 포함):

[📌 한 줄 요약]
- 문서 내용을 한두 문장으로 요약

[💬 주요 내용]
- 핵심 내용 3~6개를 불릿으로 정리
- 중요한 숫자, 날짜, 결정 사항이 있으면 함께 적기

[✅ 다음 액션 아이템]
- 문서에서 확인된, 담당자가 해야 할 일을 불릿으로 정리
- 우선순위가 있으면 (우선) 표시
- 실행할 일이 없다면 이 [✅ 다음 액션 아이템] 섹션은 아예 출력하지 말 것

[📝 기타 메모]
- 리스크, 주의사항 등 참고용 메모를 1~3줄 이내로 정리
- 특별히 남길 메모가 없다면 이 [📝 기타 메모] 섹션은 아예 출력하지 말 것

규칙:
- 출력은 반드시 위와 같은 섹션 제목 형식을 그대로 사용할 것.
- 불릿은 모두 "- "로 시작할 것.
- 불필요한 서론, 설명 문장, 인사말은 쓰지 말 것.
- 문서와 직접 관련 없는 추측은 하지 말 것.
- 전체 분량은 A4 1장 이내, 너무 장황하게 쓰지 말 것.

응답은 한국어로만 작성해 줘.
"""


async def summarize_upload(file: UploadFile, prompt: str) -> str:
    """업로드된 파일을 Gemini에 전달해 요약 텍스트를 반환한다."""

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

        response = client.models.generate_content(
            model=MODEL,
            contents=[uploaded_file, prompt],
        )

        summary_text = getattr(response, "text", "").strip()

        if not summary_text:
            raise HTTPException(status_code=500, detail="Gemini 요약 결과가 비어 있습니다.")

        return summary_text

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
