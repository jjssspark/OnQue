"""비서 컨텍스트 수집.

제일 중요한 단언은 그룹 격리다. A그룹에서 물었는데 B그룹 약속이 컨텍스트에
섞이면 정보 유출이고, 모델이 그걸 그대로 답에 옮긴다.
"""

from datetime import date, timedelta

import assistant_service
from models import (
    ChatRoom,
    ChatRoomMember,
    Client,
    Commitment,
    Group,
    GroupMembership,
    Schedule,
    Todo,
    User,
)


def _seed_group(db, name):
    user = User(email=f"{name}@onque.dev", password_hash="x", name=name)
    db.add(user)
    db.flush()
    group = Group(name=name, created_by=user.id)
    db.add(group)
    db.flush()
    db.add(GroupMembership(user_id=user.id, group_id=group.id, role="admin"))
    db.flush()
    return user, group


def _commitment(db, group_id, content, *, status="proposed", due=None, client_id=None):
    c = Commitment(
        group_id=group_id, content=content, status=status, due_date=due,
        source_type="chat", evidence="근거 원문", client_id=client_id,
    )
    db.add(c)
    db.flush()
    return c


def test_context_excludes_other_groups(db_session):
    """그룹 격리 — 이 단언이 깨지면 정보 유출이다."""
    user_a, group_a = _seed_group(db_session, "A팀")
    _, group_b = _seed_group(db_session, "B팀")

    _commitment(db_session, group_a.id, "A팀 약속")
    _commitment(db_session, group_b.id, "B팀 약속")
    db_session.add(Todo(group_id=group_a.id, content="A팀 할 일"))
    db_session.add(Todo(group_id=group_b.id, content="B팀 할 일"))
    db_session.add(Schedule(group_id=group_a.id, title="A팀 일정", scheduled_date=date.today()))
    db_session.add(Schedule(group_id=group_b.id, title="B팀 일정", scheduled_date=date.today()))
    db_session.add(Client(group_id=group_a.id, name="A고객"))
    db_session.add(Client(group_id=group_b.id, name="B고객"))
    db_session.commit()

    ctx = assistant_service.build_context(db_session, group_a.id, user_a.id)

    blob = assistant_service.render_context(ctx)
    assert "B팀" not in blob
    assert "B고객" not in blob
    assert [c["content"] for c in ctx["commitments"]] == ["A팀 약속"]
    assert [t["content"] for t in ctx["todos"]] == ["A팀 할 일"]
    assert [s["title"] for s in ctx["schedules"]] == ["A팀 일정"]
    assert ctx["clients"] == ["A고객"]


def test_context_includes_company_wide_schedules(db_session):
    """group_id가 NULL인 일정은 기존 GET /schedules가 이미 함께 보여준다.

    비서가 화면과 다른 걸 보면 답이 어긋난다.
    """
    user_a, group_a = _seed_group(db_session, "A팀")
    db_session.add(Schedule(group_id=None, title="전사 일정", scheduled_date=date.today()))
    db_session.commit()

    ctx = assistant_service.build_context(db_session, group_a.id, user_a.id)

    assert [s["title"] for s in ctx["schedules"]] == ["전사 일정"]


def test_commitments_sorted_by_due_date_with_nulls_last(db_session):
    """상한에 걸려 잘릴 때 급한 것부터 남아야 한다."""
    user, group = _seed_group(db_session, "A팀")
    today = date.today()
    _commitment(db_session, group.id, "기한 없음", due=None)
    _commitment(db_session, group.id, "나중", due=today + timedelta(days=10))
    _commitment(db_session, group.id, "급함", due=today + timedelta(days=1))
    db_session.commit()

    ctx = assistant_service.build_context(db_session, group.id, user.id)

    assert [c["content"] for c in ctx["commitments"]] == ["급함", "나중", "기한 없음"]


def test_context_respects_limits(db_session):
    user, group = _seed_group(db_session, "A팀")
    for i in range(assistant_service.CONTEXT_TODO_LIMIT + 10):
        db_session.add(Todo(group_id=group.id, content=f"할 일 {i}"))
    for i in range(assistant_service.CONTEXT_COMMITMENT_LIMIT + 10):
        _commitment(db_session, group.id, f"약속 {i}")
    db_session.commit()

    ctx = assistant_service.build_context(db_session, group.id, user.id)

    assert len(ctx["todos"]) == assistant_service.CONTEXT_TODO_LIMIT
    assert len(ctx["commitments"]) == assistant_service.CONTEXT_COMMITMENT_LIMIT


def test_done_todos_and_past_schedules_are_excluded(db_session):
    user, group = _seed_group(db_session, "A팀")
    db_session.add(Todo(group_id=group.id, content="끝난 일", is_done=True))
    db_session.add(Todo(group_id=group.id, content="남은 일", is_done=False))
    db_session.add(Schedule(group_id=group.id, title="지난 일정",
                            scheduled_date=date.today() - timedelta(days=1)))
    db_session.commit()

    ctx = assistant_service.build_context(db_session, group.id, user.id)

    assert [t["content"] for t in ctx["todos"]] == ["남은 일"]
    assert ctx["schedules"] == []


def test_confirmed_commitment_carries_due_flags(db_session):
    """proposed는 기한이 지나도 is_overdue가 False다 — 프롬프트가 이걸 알아야 한다."""
    user, group = _seed_group(db_session, "A팀")
    past = date.today() - timedelta(days=3)
    _commitment(db_session, group.id, "확정 지남", status="confirmed", due=past)
    _commitment(db_session, group.id, "미확인 지남", status="proposed", due=past)
    db_session.commit()

    ctx = assistant_service.build_context(db_session, group.id, user.id)
    by_content = {c["content"]: c for c in ctx["commitments"]}

    assert by_content["확정 지남"]["is_overdue"] is True
    assert by_content["미확인 지남"]["is_overdue"] is False


def test_client_name_is_resolved(db_session):
    user, group = _seed_group(db_session, "A팀")
    client = Client(group_id=group.id, name="A고객")
    db_session.add(client)
    db_session.flush()
    _commitment(db_session, group.id, "연결된 약속", client_id=client.id)
    _commitment(db_session, group.id, "미지정 약속", client_id=None)
    db_session.commit()

    ctx = assistant_service.build_context(db_session, group.id, user.id)
    by_content = {c["content"]: c for c in ctx["commitments"]}

    assert by_content["연결된 약속"]["client_name"] == "A고객"
    assert by_content["미지정 약속"]["client_name"] is None


def test_context_excludes_commitment_from_private_room_for_non_member(db_session):
    """C1: group_id만으로는 부족하다. 채팅방 멤버십도 함께 봐야 한다.

    owner만 초대된 비공개 방에서 나온 약속은, 같은 그룹의 outsider가 물어봐도
    build_context 결과와 render_context 평문 양쪽에서 빠져야 한다 — 안 그러면
    화면(GET /api/v1/commitments)에는 안 보이는 내용이 비서 답변으로는 샌다.
    """
    owner, group = _seed_group(db_session, "A팀")
    outsider = User(email="outsider@onque.dev", password_hash="x", name="외부인")
    db_session.add(outsider)
    db_session.flush()
    db_session.add(GroupMembership(user_id=outsider.id, group_id=group.id, role="member"))

    room = ChatRoom(group_id=group.id, name="비공개 방", created_by=owner.id)
    db_session.add(room)
    db_session.flush()
    db_session.add(ChatRoomMember(room_id=room.id, user_id=owner.id))
    db_session.flush()

    hidden = Commitment(
        group_id=group.id,
        content="비공개 방 약속 내용",
        status="confirmed",
        source_type="chat",
        room_id=room.id,
        evidence="비공개 방 원문",
        client_id=None,
    )
    db_session.add(hidden)
    db_session.commit()

    outsider_ctx = assistant_service.build_context(db_session, group.id, outsider.id)
    assert outsider_ctx["commitments"] == []
    outsider_blob = assistant_service.render_context(outsider_ctx)
    assert "비공개 방 약속 내용" not in outsider_blob

    owner_ctx = assistant_service.build_context(db_session, group.id, owner.id)
    assert [c["content"] for c in owner_ctx["commitments"]] == ["비공개 방 약속 내용"]
