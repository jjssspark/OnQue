"""약속 추출 결과를 DB에 반영하는 계층.

라우터와 요약 파이프라인 양쪽에서 쓰이므로 별도 모듈로 둔다.
"""

import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import NamedTuple
from zoneinfo import ZoneInfo

from sqlalchemy import insert, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import gemini_service
from models import (
    ChatMessage,
    ChatRoom,
    ChatRoomMember,
    Client,
    Commitment,
    Group,
    CallBudget,
    COMMITMENT_STATUSES,
)

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")

# 기한 경고 기준. D-2 이내면 임박으로 본다.
DUE_SOON_DAYS = 2

# 다이어그램에 그려진 화살표만 허용한다: proposed -> confirmed/dismissed,
# confirmed -> fulfilled/dismissed. fulfilled·dismissed는 키가 없으므로
# 종료 상태에서는 어떤 target이 와도 자연히 거부된다 — 되돌리기(undo)는 없다.
_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "proposed": frozenset({"confirmed", "dismissed"}),
    "confirmed": frozenset({"fulfilled", "dismissed"}),
}


def can_transition(current: str, target: str) -> bool:
    if target not in COMMITMENT_STATUSES:
        return False
    return target in _ALLOWED_TRANSITIONS.get(current, frozenset())


def apply_status(commitment: Commitment, target: str) -> None:
    commitment.status = target
    if target == "confirmed" and commitment.confirmed_at is None:
        commitment.confirmed_at = datetime.now(timezone.utc)


def visible_commitment_filter(user_id: int):
    """채팅방은 그룹 전원이 아니라 초대된 사람만 볼 수 있다(main.py:588
    _require_room_access와 같은 규칙). 스윕은 그룹의 모든 방을 훑어
    Commitment.evidence에 원문을 그대로 저장하므로, 조회 시점에 방 멤버십으로
    걸러야 비공개 방의 대화가 그룹 전원에게 새지 않는다.

    call/document 출처는 방 개념이 없으므로 그대로 통과시킨다. 채팅 출처는
    create_commitments 시점에 항상 room_id를 채워 저장하므로, room_id가
    NULL이라는 건 그 방이 나중에 삭제됐다는 뜻뿐이다(main.py의
    _delete_room_cascade가 삭제 시 NULL로 만든다) — 검사할 멤버십이 더는
    없으므로 그룹 공개로 승격시킨다. 조용히 영구 은닉되는 것보다 낫다고
    판단한 트레이드오프다.

    routers/commitments.py(목록 조회)와 assistant_service.py(비서 컨텍스트)가
    함께 쓴다 — 두 벌로 유지하면 한쪽만 고쳤을 때 조용히 어긋난다.
    """
    allowed_rooms = select(ChatRoomMember.room_id).where(ChatRoomMember.user_id == user_id)
    return or_(
        Commitment.source_type != "chat",
        Commitment.room_id.is_(None),
        Commitment.room_id.in_(allowed_rooms),
    )


def is_commitment_visible(db: Session, user_id: int, commitment: Commitment) -> bool:
    """단건(PATCH)·소수건(bulk) 판정용. 목록 필터(visible_commitment_filter)와
    같은 규칙을 단일 레코드에 적용한다. assistant_service의 액션 검증도 같은
    규칙을 쓴다 — 안 보이는 약속을 지목한 commitment_status 액션을 걸러낸다."""
    if commitment.source_type != "chat":
        return True
    if commitment.room_id is None:
        return True
    return db.get(ChatRoomMember, {"room_id": commitment.room_id, "user_id": user_id}) is not None


def today_kst() -> date:
    """Render는 UTC로 도는데 프롬프트는 이미 KST 기준(korean_date_context)이다.

    서버 로컬(UTC) 자정~09시 사이에는 date.today()가 여전히 어제를 가리켜
    어제 넘긴 기한이 "오늘 마감"으로 보인다. 기한 판정도 KST로 통일한다.
    """
    return datetime.now(KST).date()


def due_flags(commitment: Commitment, today: date) -> tuple[bool, bool]:
    """(is_overdue, is_due_soon). 저장하지 않고 조회 시 계산하는 파생값이다.

    proposed 상태는 아직 사람이 확인하지 않았으므로 추적 대상이 아니다.
    """
    if commitment.status != "confirmed" or commitment.due_date is None:
        return (False, False)
    delta = (commitment.due_date - today).days
    return (delta < 0, 0 <= delta <= DUE_SOON_DAYS)


def days_past_due(commitment: Commitment, today: date) -> int | None:
    """기한이 며칠 지났는지. 안 지났거나 기한이 없으면 None.

    is_overdue와 달리 status를 보지 않는다. 추적 대상이냐(proposed는 아니다)와
    기한이 지났느냐는 다른 질문이고, 비서는 후자를 짚어줘야 한다.
    """
    if commitment.due_date is None:
        return None
    delta = (today - commitment.due_date).days
    return delta if delta > 0 else None


def _parse_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def resolve_client_id(db: Session, group_id: int, client_name: str) -> int | None:
    """모델이 말한 클라이언트명을 등록된 Client와 대조한다.

    없으면 None을 돌려주고 새로 만들지 않는다. 오탈자와 환각이 클라이언트
    목록을 오염시키기 때문이다. 클라이언트 생성은 사람이 한다.
    """
    name = (client_name or "").strip()
    if not name:
        return None
    found = db.execute(
        select(Client).where(Client.group_id == group_id, Client.name == name)
    ).scalar_one_or_none()
    return found.id if found else None


def create_commitments(
    db: Session,
    group_id: int,
    items: list[dict],
    source_type: str,
    source_id: int | None,
    room_id: int | None = None,
) -> list[Commitment]:
    """추출된 약속을 proposed 상태로 저장한다. commit은 호출자가 한다.

    room_id는 채팅 출처(source_type="chat")일 때만 의미가 있다 —
    가시성 판정(routers/commitments.py)이 이 값으로 방 멤버십을 확인한다.

    채팅 출처인데 room_id가 없으면 거부한다. 새 규칙에서 NULL은 "방이
    삭제됨 → 그룹 전원 공개"를 뜻하므로, 빠뜨리면 비공개 방 대화 원문이
    조용히 전원에게 열린다. 기본값 None이 fail-open 방향이라 명시적으로 막는다.
    """
    if source_type == "chat" and room_id is None:
        raise ValueError("채팅 출처 약속에는 room_id가 필요하다")

    created: list[Commitment] = []
    for item in items:
        content = (item.get("content") or "").strip()
        evidence = (item.get("evidence") or "").strip()
        if not content or not evidence:
            continue
        commitment = Commitment(
            group_id=group_id,
            client_id=resolve_client_id(db, group_id, item.get("client_name", "")),
            content=content,
            due_date=_parse_date(item.get("due_date") or ""),
            status="proposed",
            source_type=source_type,
            source_id=source_id,
            room_id=room_id,
            evidence=evidence,
        )
        db.add(commitment)
        created.append(commitment)
    return created


SWEEP_COOLDOWN_MINUTES = 10
# 이보다 적게 쌓인 방은 훑지 않는다. 한산한 방은 영영 안 훑일 수 있으나,
# 그런 방에서 놓칠 약속은 적고 사용자는 명령어로 직접 부를 수 있다.
CHAT_SCAN_THRESHOLD = 15
# 한 번에 프롬프트에 실을 메시지 상한. 오래 밀린 방을 통째로 넣으면 토큰
# 한도로 실패하고, 실패 시 포인터를 전진시키지 않으므로 같은 실패가 매
# 스윕마다 반복된다. 상한을 두면 밀린 방도 스윕을 거듭하며 조금씩 따라잡는다.
CHAT_SCAN_BATCH_LIMIT = 100
# 스윕이 하루에 쓸 수 있는 Gemini 호출 수. 무료 티어 하루 20건 중 8건만
# 백그라운드에 준다. 나머지 12건은 사용자가 직접 올리는 파일 요약 몫이다 —
# 시킨 일이 안 시킨 일 때문에 실패하는 것이 한도 자체보다 나쁘다.
SWEEP_DAILY_BUDGET = int(os.getenv("SWEEP_DAILY_BUDGET", "8"))


def sweep_calls_used_today(db: Session) -> int:
    """오늘 스윕이 쓴 Gemini 호출 수. 아직 없으면 0."""
    used = db.execute(
        select(CallBudget.calls).where(CallBudget.day == datetime.now(timezone.utc).date())
    ).scalar_one_or_none()
    return used or 0


def _claim_sweep_call(db: Session) -> bool:
    """오늘치 예산에서 호출 1건을 선점한다. 남아 있으면 True.

    쿨다운 선점(maybe_sweep)과 같은 방식이다 — 조건부 UPDATE의 rowcount로
    판정한다. SELECT 후 UPDATE 하면 두 요청이 같은 잔량을 읽고 둘 다 통과해
    예산을 넘긴다.

    오늘 행이 아직 없으면 UPDATE가 0건이라 삽입해야 하는데, 이때 다른 요청이
    먼저 넣었으면 IntegrityError가 난다. 그대로 두면 바깥 트랜잭션(약속 목록
    조회)까지 오염되므로 SAVEPOINT 안에서 시도하고, 졌으면 UPDATE로 재시도한다.

    선점에 성공하면 곧바로 커밋한다. 이 뒤 Gemini 호출이 실패하면 maybe_sweep이
    방 단위로 rollback 하는데, 같은 트랜잭션에 묶여 있으면 차감분까지 되돌아간다.
    호출은 이미 나가서 실제 한도는 깎였는데 장부만 복구되는 셈이라, 실패하는 방
    하나가 남은 예산을 전부 태우며 재시도를 반복하게 된다.
    """
    today = datetime.now(timezone.utc).date()
    bumped = db.execute(
        update(CallBudget)
        .where(CallBudget.day == today, CallBudget.calls < SWEEP_DAILY_BUDGET)
        .values(calls=CallBudget.calls + 1)
        .execution_options(synchronize_session=False)
    )
    if bumped.rowcount == 1:
        db.commit()
        return True

    # 행이 있는데 못 올렸다면 예산 소진이다. 삽입을 시도하면 안 된다.
    if db.execute(
        select(CallBudget.day).where(CallBudget.day == today)
    ).scalar_one_or_none() is not None:
        return False

    if SWEEP_DAILY_BUDGET < 1:
        return False

    try:
        with db.begin_nested():
            db.execute(insert(CallBudget).values(day=today, calls=1))
        db.commit()
        return True
    except IntegrityError:
        # 다른 요청이 먼저 오늘 행을 만들었다. 그 행 위에서 다시 겨룬다.
        retried = db.execute(
            update(CallBudget)
            .where(CallBudget.day == today, CallBudget.calls < SWEEP_DAILY_BUDGET)
            .values(calls=CallBudget.calls + 1)
            .execution_options(synchronize_session=False)
        )
        if retried.rowcount == 1:
            db.commit()
            return True
        return False


SCAN_DONE = "scanned"
SCAN_BELOW_THRESHOLD = "below_threshold"
SCAN_NO_BUDGET = "no_budget"


class ScanResult(NamedTuple):
    """방 하나를 훑은 결과. status 외에 개수를 함께 돌려주는 이유는
    maybe_sweep이 그룹 단위 합계를 Group에 기록해야 하기 때문이다."""

    status: str
    scanned: int = 0
    found: int = 0


def _scan_room(db: Session, room: ChatRoom) -> ScanResult:
    """방 하나를 훑는다. status는 위 SCAN_* 중 하나다.

    "안 훑었다"를 한 값으로 뭉치지 않는 이유: 기준 미달은 다음 방으로 넘어가면
    되지만 예산 소진은 남은 방을 다 건너뛰어야 한다. bool로는 구분이 안 된다.

    예산은 기준을 통과한 뒤, Gemini를 부르기 직전에 선점한다. 순서가 반대면
    메시지 14개짜리 한산한 방들이 훑지도 않으면서 예산을 먼저 먹어치운다.

    실패하면 예외를 그대로 던진다. 삼키지 않는 이유는 호출자(maybe_sweep)가
    방 단위로 격리해서 잡아야 이 방의 실패가 다른 방에 번지지 않기 때문이다.
    """
    query = select(ChatMessage).where(ChatMessage.room_id == room.id)
    if room.last_scanned_message_id is not None:
        query = query.where(ChatMessage.id > room.last_scanned_message_id)
    messages = (
        db.execute(query.order_by(ChatMessage.id).limit(CHAT_SCAN_BATCH_LIMIT))
        .scalars()
        .all()
    )

    if len(messages) < CHAT_SCAN_THRESHOLD:
        return ScanResult(SCAN_BELOW_THRESHOLD)

    if not _claim_sweep_call(db):
        return ScanResult(SCAN_NO_BUDGET)

    history = "\n".join(f"{m.sender}: {m.content}" for m in messages)
    items = gemini_service.extract_chat_commitments(history)
    if items is None:
        # 모델 호출/파싱이 실패했다. "약속 없음"과 구분해 포인터를 전진시키지
        # 않아야 다음 스윕에서 같은 배치를 다시 시도한다.
        raise RuntimeError(f"채팅 약속 추출 실패: room_id={room.id}")

    created = create_commitments(
        db,
        group_id=room.group_id,
        items=items,
        source_type="chat",
        source_id=messages[-1].id,
        room_id=room.id,
    )
    room.last_scanned_message_id = messages[-1].id
    return ScanResult(SCAN_DONE, scanned=len(messages), found=len(created))


def maybe_sweep(db: Session, group_id: int) -> int:
    """요청에 편승해 돌리는 자율 점검. 스캔한 방 수를 돌려준다.

    Render 무료 티어에 상주 워커가 없어 백그라운드 스케줄러를 쓸 수 없다.
    아무도 접속하지 않으면 스윕도 안 돌지만, 그때는 알림을 볼 사람도 없다.

    쿨다운은 조건부 UPDATE로 진입 시점에 "선점"한다. 두 요청이 동시에
    들어오면 둘 다 SELECT로는 쿨다운을 통과해버려 같은 배치에 Gemini를
    두 번 부르고 같은 약속을 중복 저장할 수 있다(유니크 제약이 없다).
    UPDATE ... WHERE last_swept_at IS NULL OR < cutoff 는 원자적이라 한
    요청만 rowcount=1로 이긴다 — 진 요청은 즉시 0을 반환한다.

    방은 서로 독립적으로 처리한다. 한 방의 실패가 다른 방의 결과까지
    날려버리면, 문제 있는 방 하나가 그룹 전체의 약속 탐지를 막는다.
    쿨다운은 이미 진입 시점에 선점했으므로 방 실패와 무관하게 유지된다.

    이 함수는 절대 던지지 않는다는 보장이 없다 — 쿨다운 선점 UPDATE와
    방 목록 SELECT는 groups/chat_rooms의 매핑된 컬럼을 그대로 SELECT/UPDATE
    하므로, 스키마 전환 창이나 커넥션 풀 고갈 중이면 예외가 그대로 샌다.
    "스윕이 조회를 죽이면 안 된다"는 정책은 호출자(routers/commitments.py)의
    책임이다 — 그쪽에서 try로 감싸고 WARN을 남긴다.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=SWEEP_COOLDOWN_MINUTES)
    claimed = db.execute(
        update(Group)
        .where(
            Group.id == group_id,
            or_(Group.last_swept_at.is_(None), Group.last_swept_at < cutoff),
        )
        .values(last_swept_at=now)
        # 세션에 이미 로드된 Group을 이 WHERE로 재평가하면 SQLite가 잃어버린
        # tz 정보 때문에 naive/aware 비교 TypeError가 난다. DB에는 이미
        # UPDATE가 반영되므로 동기화는 필요 없다 — 이후 코드는 이 그룹
        # 객체의 last_swept_at을 다시 읽지 않는다.
        .execution_options(synchronize_session=False)
    )
    db.commit()
    if claimed.rowcount == 0:
        return 0

    rooms = db.execute(
        select(ChatRoom).where(ChatRoom.group_id == group_id)
    ).scalars().all()

    scanned = 0
    messages_read = 0
    commitments_found = 0
    for room in rooms:
        try:
            result = _scan_room(db, room)
            if result.status == SCAN_NO_BUDGET:
                # 남은 방을 계속 돌아봐야 전부 같은 이유로 막힌다. 여기서 끊는다.
                # 커밋은 하지 않는다 — 예산을 못 얻었으니 바꾼 것도 없다.
                logger.info(
                    "스윕 일일 예산 소진",
                    extra={
                        "event": "commitment.sweep.budget_exhausted",
                        "group_id": group_id,
                        "budget": SWEEP_DAILY_BUDGET,
                    },
                )
                break
            if result.status == SCAN_DONE:
                db.commit()
                scanned += 1
                messages_read += result.scanned
                commitments_found += result.found
        except Exception:
            db.rollback()
            logger.warning(
                "방 스캔 실패",
                extra={
                    "event": "commitment.sweep.room_failed",
                    "group_id": group_id,
                    "room_id": room.id,
                },
                exc_info=True,
            )

    # 훑은 게 하나도 없으면 직전 기록을 남겨둔다. 0으로 덮으면 화면에서
    # "방금 아무것도 못 찾음"과 "10분간 새 대화가 없음"이 구분되지 않는다.
    if scanned > 0:
        db.execute(
            update(Group)
            .where(Group.id == group_id)
            .values(
                # 시각도 같이 남긴다. 위 쿨다운 선점이 갱신하는 last_swept_at은
                # 훑을 게 없어도 올라가므로, 개수와 짝지어 보여줄 수 없다.
                last_scan_at=datetime.now(timezone.utc),
                last_sweep_scanned=messages_read,
                last_sweep_found=commitments_found,
            )
            .execution_options(synchronize_session=False)
        )
        db.commit()

    return scanned
