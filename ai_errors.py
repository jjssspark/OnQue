"""AI 한도 소진 응답. 라우터와 main이 함께 쓴다.

별도 모듈로 뺀 이유: 이 응답을 내는 곳이 네 군데인데 routers/assistant.py가
main을 import하면 순환이라, 같은 내용을 손으로 한 번 더 써두고 있었다.
한쪽만 고치면 프론트의 code 분기가 경로에 따라 갈린다.
"""

from typing import NoReturn

from fastapi import HTTPException


def raise_ai_budget_exhausted() -> NoReturn:
    """소진 응답은 전 경로가 같아야 한다. 프론트는 message가 아니라 code로
    분기하므로 경로마다 코드가 다르면 화면이 소진을 한 가지로 다룰 수 없다.

    500이 아니라 429인 이유: 요약·비서·채팅이 같은 무료 티어 할당량을 나눠
    써서 사용자는 몇 건 만에 이 상태를 만난다. 일반 서버 오류로 보이면 파일이
    잘못됐다고 생각하고 다른 파일로 계속 재시도한다.
    """
    raise HTTPException(
        status_code=429,
        detail={
            "code": "AI_DAILY_BUDGET_EXHAUSTED",
            "message": "오늘 AI 한도를 다 썼습니다. 내일 다시 이용해주세요.",
        },
    )
