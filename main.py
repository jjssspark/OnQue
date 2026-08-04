import os
import tempfile

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import google.generativeai as genai

# .env 에서 GOOGLE_API_KEY 읽기
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    raise RuntimeError("GOOGLE_API_KEY 환경변수가 설정되어 있지 않습니다.")

# Gemini API 설정
genai.configure(api_key=GOOGLE_API_KEY)

app = FastAPI()

# CORS 설정 (프론트엔드에서 호출 가능하게)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 개발 중이라 전체 허용, 나중엔 도메인 제한 추천
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def health_check():
    return {"status": "ok", "message": "OnQue FastAPI with Gemini"}


@app.post("/summarize-call")
async def summarize_call(file: UploadFile = File(...)):
    """
    통화 녹음 파일(mp3, m4a, wav 등)을 받아서
    Gemini로 요약한 결과를 반환하는 엔드포인트
    """

    # 1) 파일 타입 체크
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(
            status_code=400,
            detail=f"오디오 파일만 업로드 가능합니다. (현재 content_type: {file.content_type})",
        )

    # 2) 업로드된 파일을 임시 경로에 저장
    try:
        suffix = os.path.splitext(file.filename)[1]  # 예: ".mp3"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            temp_path = tmp.name
            content = await file.read()
            tmp.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 저장 중 오류: {e}")

    try:
        # 3) Gemini에 파일 업로드
        uploaded_file = genai.upload_file(path=temp_path)

        # 요약 프롬프트
        prompt = """
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


        model = genai.GenerativeModel("gemini-2.5-flash")

        # 🔥 업로드된 파일 객체 + 프롬프트를 함께 전달
        response = model.generate_content([uploaded_file, prompt])

        summary_text = getattr(response, "text", "").strip()

        if not summary_text:
            raise HTTPException(status_code=500, detail="Gemini 요약 결과가 비어 있습니다.")

        # 프론트엔드에서 기대하는 형태로 응답
        return {
            "filename": file.filename,
            "summary": summary_text,
        }

    except Exception as e:
        # Gemini 쪽 에러를 표시
        raise HTTPException(status_code=500, detail=f"Gemini 요약 중 오류: {e}")

    finally:
        # 4) 임시 파일 삭제
        try:
            os.remove(temp_path)
        except Exception:
            pass
