"""시연용 데모 데이터를 채우는 스크립트.

발표 전 백엔드 깨우기(Render 무료 티어 콜드스타트 실측 39초):
    curl -s -o /dev/null -w "%{http_code} %{time_total}s\\n" <백엔드주소>/api/v1/groups
401이 돌아오면 정상이다 — 서버는 살아 있고 인증만 없는 상태다.
"""

import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# scripts/를 직접 실행해도 저장소 루트의 models·db를 찾게 한다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, func, select

from models import Client, Commitment, Document, Schedule, Todo

CLIENT_NAMES = ("한빛물산", "대성기업", "서진테크")

# 삭제 순서는 참조 방향의 역순이다. commitments.client_id가 clients를 참조하므로
# clients를 먼저 지우면 FK 위반으로 죽는다.
CONTENT_MODELS = (Commitment, Todo, Schedule, Document, Client)


@dataclass(frozen=True)
class DemoData:
    clients: tuple[str, ...]
    documents: tuple[dict, ...]
    commitments: tuple[dict, ...]
    todos: tuple[dict, ...]
    schedules: tuple[dict, ...]


def _day(today: date, offset: int) -> date:
    return today + timedelta(days=offset)


def _ts(today: date, offset: int) -> datetime:
    """created_at용 UTC 타임스탬프. 정오로 고정해 같은 날 항목의 정렬이 흔들리지 않게 한다."""
    d = _day(today, offset)
    return datetime(d.year, d.month, d.day, 12, tzinfo=timezone.utc)


def build_demo_data(today: date) -> DemoData:
    """오늘을 기준으로 데모 데이터를 만든다.

    절대 날짜를 쓰지 않는다. 다음 주에 돌려도 '7일 지남'은 여전히 7일 지남이고
    '마감 임박'은 여전히 임박이라, 언제 시연해도 같은 화면이 나온다.

    client_index는 삽입 시점에 실제 client_id로 바뀐다. 여기서는 DB를 모른다.
    """
    documents = (
        {
            "source_type": "call",
            "category": "기타",
            "filename": "통화_한빛물산_0730.m4a",
            "summary": "한빛물산 김 과장과 통화. 재고 확인 후 견적서를 다시 보내기로 함. 납기는 2주 예상.",
            "created_at": _ts(today, -14),
        },
        {
            "source_type": "document",
            "category": "기획",
            "filename": "대성기업_견적서.pdf",
            "summary": "대성기업 견적서 검토. 단가는 합의 범위이나 결제 조건이 기존과 다름. 계약 전 확인 필요.",
            "created_at": _ts(today, -9),
        },
        {
            "source_type": "call",
            "category": "기타",
            "filename": "통화_서진테크_0808.m4a",
            "summary": "서진테크 담당자 교체 안내. 신규 담당자에게 단가표를 다시 전달하기로 함.",
            "created_at": _ts(today, -5),
        },
        {
            "source_type": "document",
            "category": "개발",
            "filename": "회의록_주간점검.txt",
            "summary": "주간 점검 회의록. 이번 주 배포 일정과 이슈 세 건을 정리함. 다음 점검은 다음 주 동일 시간.",
            "created_at": _ts(today, -2),
        },
    )

    commitments = (
        {
            "status": "proposed",
            "due_date": _day(today, 1),
            "client_index": 0,
            "source_type": "call",
            "content": "한빛물산에 수정 견적서 회신",
            "evidence": "통화 중 '내일까지 다시 보내드릴게요'라고 말함",
            "created_at": _ts(today, -1),
        },
        {
            "status": "proposed",
            "due_date": _day(today, 5),
            "client_index": 1,
            "source_type": "document",
            "content": "대성기업 결제 조건 확인 후 회신",
            "evidence": "견적서 하단 결제 조건이 기존 계약과 다름",
            "created_at": _ts(today, -2),
        },
        {
            "status": "proposed",
            "due_date": None,
            "client_index": None,
            "source_type": "chat",
            "content": "서진테크 신규 담당자 연락처 확보",
            "evidence": "채팅에서 '담당자 바뀌었대요'라고 언급됨",
            "created_at": _ts(today, -3),
        },
        {
            "status": "confirmed",
            "due_date": _day(today, -7),
            "client_index": 0,
            "source_type": "call",
            "content": "한빛물산 샘플 발송",
            "evidence": "통화 중 '이번 주 안에 샘플 보내드리겠습니다'라고 약속함",
            "created_at": _ts(today, -10),
        },
        {
            "status": "confirmed",
            "due_date": _day(today, -2),
            "client_index": 2,
            "source_type": "call",
            "content": "서진테크 신규 단가표 전달",
            "evidence": "담당자 교체 통화에서 단가표 재전달을 약속함",
            "created_at": _ts(today, -5),
        },
        {
            "status": "confirmed",
            "due_date": _day(today, 1),
            "client_index": 1,
            "source_type": "document",
            "content": "대성기업 납기 확정 회신",
            "evidence": "견적서에 납기 확정 회신 요청이 명시됨",
            "created_at": _ts(today, -4),
        },
        {
            "status": "confirmed",
            "due_date": _day(today, 10),
            "client_index": 2,
            "source_type": "chat",
            "content": "서진테크 정기 점검 일정 조율",
            "evidence": "채팅에서 다음 달 점검 일정을 잡기로 함",
            "created_at": _ts(today, -6),
        },
        {
            "status": "fulfilled",
            "due_date": _day(today, -3),
            "client_index": 0,
            "source_type": "call",
            "content": "한빛물산 계약서 날인본 회수",
            "evidence": "통화에서 날인 후 회수하기로 함",
            "created_at": _ts(today, -12),
        },
        {
            "status": "dismissed",
            "due_date": _day(today, -5),
            "client_index": 1,
            "source_type": "document",
            "content": "대성기업 추가 할인 검토",
            "evidence": "견적서 여백에 할인 문의가 적혀 있었으나 내부 검토에서 반려",
            "created_at": _ts(today, -11),
        },
    )

    todos = (
        {"content": "한빛물산 재고 확인 회신", "due_date": _day(today, -7), "is_done": False, "created_at": _ts(today, -9)},
        {"content": "대성기업 세금계산서 발행", "due_date": _day(today, -3), "is_done": False, "created_at": _ts(today, -6)},
        {"content": "서진테크 방문 일정 확정", "due_date": _day(today, 1), "is_done": False, "created_at": _ts(today, -3)},
        {"content": "주간 보고서 초안 작성", "due_date": _day(today, 2), "is_done": False, "created_at": _ts(today, -2)},
        {"content": "하반기 단가표 개정", "due_date": _day(today, 10), "is_done": False, "created_at": _ts(today, -4)},
        {"content": "받은 명함 정리", "due_date": None, "is_done": False, "created_at": _ts(today, -1)},
        {"content": "월간 정산 마감", "due_date": _day(today, -1), "is_done": True, "created_at": _ts(today, -8)},
        {"content": "회의실 예약", "due_date": None, "is_done": True, "created_at": _ts(today, -7)},
    )

    schedules = (
        {"title": "한빛물산 방문", "scheduled_date": _day(today, 1)},
        {"title": "대성기업 화상회의", "scheduled_date": _day(today, 3)},
        {"title": "주간 팀 점검", "scheduled_date": _day(today, 6)},
        {"title": "분기 리뷰", "scheduled_date": _day(today, 20)},
    )

    return DemoData(
        clients=CLIENT_NAMES,
        documents=documents,
        commitments=commitments,
        todos=todos,
        schedules=schedules,
    )


def count_demo_content(session, group_id: int) -> dict[str, int]:
    """지울 대상 건수를 테이블별로 센다. 실행 전 사용자에게 보여주는 용도다."""
    return {
        model.__tablename__: session.scalar(
            select(func.count()).select_from(model).where(model.group_id == group_id)
        )
        for model in CONTENT_MODELS
    }


def clear_demo_content(session, group_id: int) -> dict[str, int]:
    """대상 그룹의 콘텐츠만 지운다.

    사용자·그룹 멤버십·그룹·초대 기록은 건드리지 않는다. 시연 팀에는 초대로
    들어온 실제 동료 계정이 있고, 시드를 다시 돌릴 때 그 사람들이 튕겨나가면
    다시 초대해야 한다.

    커밋하지 않는다. 호출자가 삽입까지 한 트랜잭션으로 묶는다.
    """
    deleted: dict[str, int] = {}
    for model in CONTENT_MODELS:
        result = session.execute(delete(model).where(model.group_id == group_id))
        deleted[model.__tablename__] = result.rowcount
    return deleted


def seed_demo(session, group_id: int, today: date) -> dict[str, int]:
    """대상 그룹의 콘텐츠를 지우고 데모 데이터로 채운다.

    커밋하지 않는다. 호출자가 커밋한다 - 삭제와 삽입이 한 트랜잭션이어야
    중간에 실패했을 때 반쯤 지워진 상태로 남지 않는다.
    """
    clear_demo_content(session, group_id)
    data = build_demo_data(today)

    clients = [Client(group_id=group_id, name=name) for name in data.clients]
    session.add_all(clients)
    session.flush()  # client_id를 얻어야 약속을 연결할 수 있다
    client_ids = [c.id for c in clients]

    for row in data.documents:
        session.add(Document(group_id=group_id, is_template=False, **row))

    for row in data.commitments:
        index = row["client_index"]
        session.add(
            Commitment(
                group_id=group_id,
                client_id=None if index is None else client_ids[index],
                content=row["content"],
                due_date=row["due_date"],
                status=row["status"],
                source_type=row["source_type"],
                evidence=row["evidence"],
                created_at=row["created_at"],
            )
        )

    for row in data.todos:
        session.add(Todo(group_id=group_id, **row))

    for row in data.schedules:
        session.add(Schedule(group_id=group_id, **row))

    session.flush()
    return count_demo_content(session, group_id)
