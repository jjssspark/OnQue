import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import assistant_service
import gemini_service
from auth import get_current_user
from db import get_db
from models import User
from permissions import require_group_member

router = APIRouter(prefix="/api/v1", tags=["assistant"])

logger = logging.getLogger(__name__)


class HistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class AssistantMessageBody(BaseModel):
    group_id: int
    message: str = Field(min_length=1, max_length=2000)
    history: list[HistoryTurn] = Field(default_factory=list)


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

    context = assistant_service.build_context(db, body.group_id)
    # 상한 초과를 422로 거절하지 않는다. 대화가 길어진 건 사용자 잘못이 아니다.
    history = [t.model_dump() for t in body.history][-assistant_service.HISTORY_MESSAGE_LIMIT:]

    answer = gemini_service.answer_assistant(
        assistant_service.render_context(context), history, body.message
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
        db, body.group_id, answer["actions"]
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
