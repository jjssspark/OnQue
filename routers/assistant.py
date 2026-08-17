import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import assistant_service
import call_budget
import gemini_service
from auth import get_current_user
from db import get_db
from models import User
from permissions import require_group_member

router = APIRouter(prefix="/api/v1", tags=["assistant"])

logger = logging.getLogger(__name__)


class HistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=2000)


class AssistantMessageBody(BaseModel):
    group_id: int
    message: str = Field(min_length=1, max_length=2000)
    # 항목 수 상한(100)은 명백한 남용만 막는 안전망이다. 실제 프롬프트에 실리는
    # 개수는 여전히 HISTORY_MESSAGE_LIMIT([-20:] 슬라이스)로 정해진다 — 상한
    # 초과를 422로 거절하지 않는다는 원칙은 그대로 유지한다.
    history: list[HistoryTurn] = Field(default_factory=list, max_length=100)


@router.post("/assistant/messages")
def send_assistant_message(
    body: AssistantMessageBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """비서에게 묻는다. 이 엔드포인트는 DB를 쓰지 않는다 — 읽고 제안만 한다.

    실제 변경은 프론트가 기존 엔드포인트(/todos, /schedules,
    /api/v1/commitments/bulk-status)로 실행한다. 권한 검사와 상태 전이
    규칙을 두 벌로 유지하지 않기 위해서다.
    """
    require_group_member(current_user, body.group_id, db)

    context = assistant_service.build_context(db, body.group_id, current_user.id)
    # 상한 초과를 422로 거절하지 않는다. 대화가 길어진 건 사용자 잘못이 아니다.
    history = [t.model_dump() for t in body.history][-assistant_service.HISTORY_MESSAGE_LIMIT:]

    try:
        answer = gemini_service.answer_assistant(
            assistant_service.render_context(context),
            history,
            body.message,
            claim=call_budget.user_claimer(),
        )
    except gemini_service.QuotaExceeded:
        # 502가 아니라 429다. 일시적 오류가 아니라 사용량이 초기화될 때까지
        # 계속 실패하는 상태라, "잠시 후 다시"로 안내하면 사용자가 재시도를
        # 반복하다 앱이 고장난 줄 안다.
        raise HTTPException(
            status_code=429,
            detail={
                "code": "ASSISTANT_QUOTA_EXCEEDED",
                "message": "AI 호출 한도를 모두 썼습니다. 사용량이 초기화된 뒤 다시 이용해주세요.",
            },
        )
    if answer is None:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "ASSISTANT_UNAVAILABLE",
                "message": "비서가 응답하지 못했습니다. 잠시 후 다시 시도해주세요.",
            },
        )

    actions, dropped = assistant_service.validate_actions(
        db, body.group_id, answer["actions"], current_user.id
    )
    reply = answer["reply"]
    if dropped:
        # 조용히 사라지면 사용자는 비서가 요청을 무시했다고 생각한다.
        reply = f"{reply}\n\n(일부 제안은 적용할 수 없어 제외했습니다.)"
        logger.warning(
            "비서 액션 일부 제외",
            extra={"event": "assistant.actions.dropped", "group_id": body.group_id},
        )

    return {"success": True, "data": {"reply": reply, "actions": actions}, "error": None}
