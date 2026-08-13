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

CLIENT_NAMES = ("한빛물산", "대성기업", "서진테크")


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
