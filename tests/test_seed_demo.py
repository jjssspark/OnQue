import json
from datetime import date

import pytest

from gemini_service import SUMMARY_PRIORITIES
from models import Client, Commitment, DOCUMENT_CATEGORIES, Group, GroupMembership, Schedule, Todo, User
from scripts.seed_demo import build_demo_data, clear_demo_content, count_demo_content, main, seed_demo

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
    """손으로 베낀 값 목록이 아니라 실제 DB CHECK 제약(DOCUMENT_CATEGORIES)을 기준으로 삼는다.
    한 번 여기서 값이 어긋난 적이 있다 — 스키마가 바뀌면 이 테스트도 같이 따라가야 한다."""
    data = build_demo_data(TODAY)
    assert all(d["category"] in DOCUMENT_CATEGORIES for d in data.documents)


def test_통화_문서의_카테고리는_통화다():
    """main.py가 실제 통화 업로드에 항상 category="통화"를 하드코딩한다.
    시드 데이터가 다른 값을 쓰면 /history의 통화 필터 칩에서 사라진다."""
    data = build_demo_data(TODAY)
    call_docs = [d for d in data.documents if d["source_type"] == "call"]
    assert call_docs
    assert all(d["category"] == "통화" for d in call_docs)


def test_요약_json이_정상화된_구조와_같은_모양이다():
    """gemini_service.normalize_summary가 만드는 것과 같은 7개 키가 다 있는지,
    action_items 항목 모양이 실제 파이프라인과 같은지 확인한다.
    프론트(SummaryReport.tsx)는 이 키들이 없으면 그대로 죽는다."""
    expected_keys = {
        "category", "headline", "key_points", "requests",
        "action_items", "notes", "commitments",
    }
    data = build_demo_data(TODAY)
    for doc in data.documents:
        structured = json.loads(doc["summary_json"])
        assert set(structured.keys()) == expected_keys
        for item in structured["action_items"]:
            assert set(item.keys()) == {"content", "due_date", "priority"}
            assert item["priority"] in SUMMARY_PRIORITIES


def test_통화_문서의_요약_json_카테고리는_기타다():
    """normalize_summary는 _CLASSIFIABLE_CATEGORIES 밖의 값(통화 포함)을 전부 "기타"로
    보정한다. 컬럼은 "통화"이지만 summary_json 안쪽 category는 "기타"여야 실제
    파이프라인이 저장했을 값과 같다."""
    data = build_demo_data(TODAY)
    call_docs = [d for d in data.documents if d["source_type"] == "call"]
    for doc in call_docs:
        structured = json.loads(doc["summary_json"])
        assert structured["category"] == "기타"


@pytest.fixture()
def group_with_member(db_session):
    """그룹 하나와 그 안의 멤버 하나. 시드가 사람을 안 지우는지 확인하는 데 쓴다."""
    user = User(email="demo@example.com", password_hash="x", name="데모")
    db_session.add(user)
    db_session.flush()
    group = Group(name="시연팀", created_by=user.id)
    db_session.add(group)
    db_session.flush()
    db_session.add(GroupMembership(group_id=group.id, user_id=user.id, role="admin"))
    db_session.commit()
    return group, user


def _put_content(session, group_id):
    session.add(Client(group_id=group_id, name="지울 클라이언트"))
    session.add(Todo(group_id=group_id, content="지울 할 일"))
    session.add(Schedule(group_id=group_id, title="지울 일정", scheduled_date=TODAY))
    session.add(
        Commitment(
            group_id=group_id,
            content="지울 약속",
            status="proposed",
            source_type="call",
            evidence="근거",
        )
    )
    session.commit()


def test_콘텐츠를_지운다(db_session, group_with_member):
    group, _ = group_with_member
    _put_content(db_session, group.id)

    clear_demo_content(db_session, group.id)
    db_session.commit()

    assert count_demo_content(db_session, group.id) == {
        "commitments": 0,
        "todos": 0,
        "schedules": 0,
        "documents": 0,
        "clients": 0,
    }


def test_사람과_멤버십은_안_지운다(db_session, group_with_member):
    """이 설계에서 가장 중요한 안전 요건이다. 동료가 튕겨나가면 안 된다."""
    group, user = group_with_member
    _put_content(db_session, group.id)

    clear_demo_content(db_session, group.id)
    db_session.commit()

    assert db_session.get(User, user.id) is not None
    assert db_session.get(Group, group.id) is not None
    memberships = db_session.query(GroupMembership).filter_by(group_id=group.id).count()
    assert memberships == 1


def test_다른_그룹은_안_건드린다(db_session, group_with_member):
    group, user = group_with_member
    other = Group(name="남의 팀", created_by=user.id)
    db_session.add(other)
    db_session.commit()
    _put_content(db_session, group.id)
    _put_content(db_session, other.id)

    clear_demo_content(db_session, group.id)
    db_session.commit()

    counts = count_demo_content(db_session, other.id)
    assert counts["todos"] == 1
    assert counts["commitments"] == 1
    assert counts["clients"] == 1


def test_넣은_뒤_건수가_맞는다(db_session, group_with_member):
    group, _ = group_with_member
    seed_demo(db_session, group.id, TODAY)
    db_session.commit()

    counts = count_demo_content(db_session, group.id)
    assert counts["clients"] == 3
    assert counts["documents"] == 4
    assert counts["commitments"] == 9
    assert counts["todos"] == 8
    assert counts["schedules"] == 4


def test_두_번_돌려도_같은_상태다(db_session, group_with_member):
    """리허설을 몇 번 해도 한 번 더 돌리면 처음 상태로 돌아가야 한다."""
    group, _ = group_with_member
    seed_demo(db_session, group.id, TODAY)
    db_session.commit()
    first = count_demo_content(db_session, group.id)

    seed_demo(db_session, group.id, TODAY)
    db_session.commit()
    second = count_demo_content(db_session, group.id)

    assert first == second


def test_약속이_클라이언트에_연결된다(db_session, group_with_member):
    group, _ = group_with_member
    seed_demo(db_session, group.id, TODAY)
    db_session.commit()

    linked = (
        db_session.query(Commitment)
        .filter(Commitment.group_id == group.id, Commitment.client_id.isnot(None))
        .count()
    )
    assert linked == 8  # client_index가 None인 약속 1건만 미연결


def test_재실행이_멤버십을_안_건드린다(db_session, group_with_member):
    group, user = group_with_member
    seed_demo(db_session, group.id, TODAY)
    db_session.commit()
    seed_demo(db_session, group.id, TODAY)
    db_session.commit()

    assert db_session.get(User, user.id) is not None
    assert db_session.query(GroupMembership).filter_by(group_id=group.id).count() == 1


def test_그룹_미지정이면_거부한다():
    """대상을 안 정한 채 지우는 스크립트가 도는 것을 막는다."""
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code != 0


def test_확인_프롬프트에서_취소하면_DB가_그대로다(db_session, group_with_member, monkeypatch):
    """'n'을 입력하면 아무것도 지우지도 채우지도 않아야 한다."""
    import db
    from tests.conftest import TestSessionLocal

    group, _ = group_with_member
    _put_content(db_session, group.id)
    before = count_demo_content(db_session, group.id)

    monkeypatch.setattr(db, "SessionLocal", TestSessionLocal)
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")

    code = main(["--group-id", str(group.id)])

    assert code == 0
    after = count_demo_content(db_session, group.id)
    assert after == before


def test_yes_플래그가_확인없이_채운다(db_session, group_with_member, monkeypatch):
    """--yes면 프롬프트 없이 바로 지우고 채워야 한다."""
    import db
    from tests.conftest import TestSessionLocal

    group, user = group_with_member
    monkeypatch.setattr(db, "SessionLocal", TestSessionLocal)

    code = main(["--group-id", str(group.id), "--yes"])

    assert code == 0
    counts = count_demo_content(db_session, group.id)
    assert counts["clients"] == 3
    assert counts["documents"] == 4
    assert counts["commitments"] == 9
    assert counts["todos"] == 8
    assert counts["schedules"] == 4

    assert db_session.get(User, user.id) is not None
    assert db_session.query(GroupMembership).filter_by(group_id=group.id).count() == 1
