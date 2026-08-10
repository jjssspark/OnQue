"""모델이 낸 액션을 서버가 검증한다.

모델은 없는 id를 지어낼 수 있고, 불법 전이를 제안할 수 있다. 그대로 내려보내면
사용자가 승인을 눌렀을 때 자기 잘못이 아닌 실패를 본다.
"""

import assistant_service
from models import ChatRoom, ChatRoomMember, Commitment, Group, GroupMembership, Schedule, Todo, User


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


def _commitment(db, group_id, content, status="confirmed"):
    c = Commitment(
        group_id=group_id, content=content, status=status,
        source_type="chat", evidence="근거",
    )
    db.add(c)
    db.flush()
    return c


def test_add_actions_are_safe(db_session):
    user, group = _seed_group(db_session, "A팀")
    db_session.commit()

    actions, dropped = assistant_service.validate_actions(
        db_session, group.id,
        [{"kind": "todo_add", "content": "시안 정리", "due_date": "2026-08-20"}],
        user.id,
    )

    assert dropped == 0
    assert actions[0]["risk"] == "safe"
    assert actions[0]["payload"] == {"content": "시안 정리", "due_date": "2026-08-20"}
    assert actions[0]["warning"] is None
    assert actions[0]["id"]


def test_delete_and_status_actions_need_confirmation(db_session):
    user, group = _seed_group(db_session, "A팀")
    todo = Todo(group_id=group.id, content="지울 일")
    db_session.add(todo)
    commitment = _commitment(db_session, group.id, "완료할 약속")
    db_session.commit()

    actions, dropped = assistant_service.validate_actions(
        db_session, group.id,
        [
            {"kind": "todo_delete", "todo_id": todo.id},
            {"kind": "commitment_status", "commitment_id": commitment.id, "to_status": "fulfilled"},
        ],
        user.id,
    )

    assert dropped == 0
    assert [a["risk"] for a in actions] == ["confirm", "confirm"]
    # 되돌릴 수 없는 전이에는 경고가 붙는다.
    assert "되돌릴 수 없" in actions[1]["warning"]


def test_todo_done_is_safe_because_it_toggles_back(db_session):
    user, group = _seed_group(db_session, "A팀")
    todo = Todo(group_id=group.id, content="끝낼 일")
    db_session.add(todo)
    db_session.commit()

    actions, _ = assistant_service.validate_actions(
        db_session, group.id, [{"kind": "todo_done", "todo_id": todo.id}], user.id
    )

    assert actions[0]["risk"] == "safe"


def test_unknown_id_is_dropped(db_session):
    user, group = _seed_group(db_session, "A팀")
    db_session.commit()

    actions, dropped = assistant_service.validate_actions(
        db_session, group.id, [{"kind": "todo_delete", "todo_id": 99999}], user.id
    )

    assert actions == []
    assert dropped == 1


def test_other_groups_id_is_dropped(db_session):
    """타 그룹 id를 지목하면 버린다 — 통과시키면 남의 데이터를 지운다."""
    user_a, group_a = _seed_group(db_session, "A팀")
    _, group_b = _seed_group(db_session, "B팀")
    foreign = _commitment(db_session, group_b.id, "B팀 약속")
    foreign_todo = Todo(group_id=group_b.id, content="B팀 할 일")
    db_session.add(foreign_todo)
    db_session.commit()

    actions, dropped = assistant_service.validate_actions(
        db_session, group_a.id,
        [
            {"kind": "commitment_status", "commitment_id": foreign.id, "to_status": "fulfilled"},
            {"kind": "todo_delete", "todo_id": foreign_todo.id},
        ],
        user_a.id,
    )

    assert actions == []
    assert dropped == 2


def test_illegal_transition_is_dropped(db_session):
    """proposed -> fulfilled 는 _ALLOWED_TRANSITIONS에 없다."""
    user, group = _seed_group(db_session, "A팀")
    commitment = _commitment(db_session, group.id, "미확인 약속", status="proposed")
    db_session.commit()

    actions, dropped = assistant_service.validate_actions(
        db_session, group.id,
        [{"kind": "commitment_status", "commitment_id": commitment.id, "to_status": "fulfilled"}],
        user.id,
    )

    assert actions == []
    assert dropped == 1


def test_unknown_kind_is_dropped(db_session):
    user, group = _seed_group(db_session, "A팀")
    db_session.commit()

    actions, dropped = assistant_service.validate_actions(
        db_session, group.id, [{"kind": "drop_database"}], user.id
    )

    assert actions == []
    assert dropped == 1


def test_add_action_without_content_is_dropped(db_session):
    user, group = _seed_group(db_session, "A팀")
    db_session.commit()

    actions, dropped = assistant_service.validate_actions(
        db_session, group.id,
        [{"kind": "todo_add", "content": "   "}, {"kind": "schedule_add", "title": "회의"}],
        user.id,
    )

    # 내용이 빈 할 일, 날짜 없는 일정 둘 다 버린다.
    assert actions == []
    assert dropped == 2


def test_validation_does_not_write_to_db(db_session):
    user, group = _seed_group(db_session, "A팀")
    todo = Todo(group_id=group.id, content="그대로 남을 일")
    db_session.add(todo)
    db_session.commit()

    assistant_service.validate_actions(
        db_session, group.id, [{"kind": "todo_delete", "todo_id": todo.id}], user.id
    )

    assert db_session.get(Todo, todo.id) is not None


def test_action_beyond_max_is_dropped(db_session):
    """모델이 할 일 수십 건에 한꺼번에 안전 액션을 내도, 프론트가 순차 자동
    실행하는 건 MAX_ACTIONS(10)개까지만이어야 한다. 초과분은 dropped로 잡힌다."""
    user, group = _seed_group(db_session, "A팀")
    todos = [Todo(group_id=group.id, content=f"할 일 {i}") for i in range(12)]
    db_session.add_all(todos)
    db_session.commit()

    raw_actions = [{"kind": "todo_done", "todo_id": t.id} for t in todos]
    actions, dropped = assistant_service.validate_actions(
        db_session, group.id, raw_actions, user.id
    )

    assert len(actions) == assistant_service.MAX_ACTIONS
    assert dropped == len(todos) - assistant_service.MAX_ACTIONS


def test_commitment_status_action_on_hidden_commitment_is_dropped(db_session):
    """C1: 비공개 방 출처 약속을 지목한 commitment_status 액션은, 그 방 멤버가
    아닌 사용자에게는 카드를 만들지 않고 dropped 처리해야 한다. 그대로 카드를
    만들면 라벨·payload에 content·client_name이 노출된 뒤에야 실행 시점(bulk-status)
    403으로 막힌다 — 노출은 이미 끝난 뒤라 너무 늦다."""
    owner, group = _seed_group(db_session, "A팀")
    outsider = User(email="outsider2@onque.dev", password_hash="x", name="외부인2")
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
        content="비공개 약속",
        status="confirmed",
        source_type="chat",
        room_id=room.id,
        evidence="비공개 원문",
    )
    db_session.add(hidden)
    db_session.commit()

    outsider_actions, outsider_dropped = assistant_service.validate_actions(
        db_session, group.id,
        [{"kind": "commitment_status", "commitment_id": hidden.id, "to_status": "fulfilled"}],
        outsider.id,
    )
    assert outsider_actions == []
    assert outsider_dropped == 1

    owner_actions, owner_dropped = assistant_service.validate_actions(
        db_session, group.id,
        [{"kind": "commitment_status", "commitment_id": hidden.id, "to_status": "fulfilled"}],
        owner.id,
    )
    assert owner_dropped == 0
    assert owner_actions[0]["payload"]["commitment_id"] == hidden.id
