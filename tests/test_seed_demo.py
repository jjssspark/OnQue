from datetime import date

from scripts.seed_demo import build_demo_data

TODAY = date(2026, 8, 13)


def test_기한_지난_할일이_둘이다():
    data = build_demo_data(TODAY)
    overdue = [t for t in data.todos if t["due_date"] and t["due_date"] < TODAY and not t["is_done"]]
    assert len(overdue) == 2


def test_마감_임박_할일이_둘이다():
    """DUE_SOON_DAYS가 2라 오늘+1, 오늘+2가 임박이다."""
    data = build_demo_data(TODAY)
    soon = [
        t for t in data.todos
        if t["due_date"] and TODAY <= t["due_date"] <= date(2026, 8, 15) and not t["is_done"]
    ]
    assert len(soon) == 2


def test_기한_없는_미완료_할일이_하나다():
    data = build_demo_data(TODAY)
    undated = [t for t in data.todos if t["due_date"] is None and not t["is_done"]]
    assert len(undated) == 1


def test_열린_약속이_일곱이다():
    """proposed 3 + confirmed 4. fulfilled·dismissed는 스트림에 안 나온다."""
    data = build_demo_data(TODAY)
    open_ones = [c for c in data.commitments if c["status"] in ("proposed", "confirmed")]
    assert len(open_ones) == 7


def test_종료된_약속도_들어간다():
    """스트림에서 걸러지는 것을 시연으로 보이려면 데이터에는 있어야 한다."""
    data = build_demo_data(TODAY)
    closed = [c for c in data.commitments if c["status"] in ("fulfilled", "dismissed")]
    assert len(closed) == 2


def test_약속_출처가_세_종류_다_있다():
    data = build_demo_data(TODAY)
    assert {c["source_type"] for c in data.commitments} == {"call", "document", "chat"}


def test_칠일_내_일정이_셋이다():
    data = build_demo_data(TODAY)
    within = [s for s in data.schedules if TODAY <= s["scheduled_date"] <= date(2026, 8, 20)]
    assert len(within) == 3


def test_열린_항목이_스트림_상한을_넘는다():
    """대시보드가 8건까지 보여준다. 화면이 가득 차야 정렬이 일하는 게 보인다."""
    data = build_demo_data(TODAY)
    open_commitments = [c for c in data.commitments if c["status"] in ("proposed", "confirmed")]
    open_todos = [t for t in data.todos if not t["is_done"]]
    assert len(open_commitments) + len(open_todos) > 8


def test_날짜가_오늘을_따라_움직인다():
    """절대 날짜를 박으면 다음 주 시연에서 정렬이 어긋난다."""
    a = build_demo_data(date(2026, 8, 13))
    b = build_demo_data(date(2026, 9, 20))
    a_overdue = sorted(t["due_date"] for t in a.todos if t["due_date"] and t["due_date"] < date(2026, 8, 13))
    b_overdue = sorted(t["due_date"] for t in b.todos if t["due_date"] and t["due_date"] < date(2026, 9, 20))
    assert a_overdue != b_overdue
    assert len(a_overdue) == len(b_overdue)


def test_약속_필수필드가_비지_않는다():
    """evidence와 source_type은 NOT NULL이다."""
    data = build_demo_data(TODAY)
    for c in data.commitments:
        assert c["content"]
        assert c["evidence"]
        assert c["source_type"]


def test_문서_카테고리가_유효값이다():
    valid = {"기획", "디자인", "개발", "마케팅", "기타"}
    data = build_demo_data(TODAY)
    assert all(d["category"] in valid for d in data.documents)
