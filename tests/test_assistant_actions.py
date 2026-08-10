"""모델이 낸 액션을 서버가 검증한다.

모델은 없는 id를 지어낼 수 있고, 불법 전이를 제안할 수 있다. 그대로 내려보내면
사용자가 승인을 눌렀을 때 자기 잘못이 아닌 실패를 본다.
"""

import assistant_service
from models import Commitment, Group, GroupMembership, Schedule, Todo, User


def _seed_group(db, name):
    user = User(email=f"{name}@onque.dev", password_hash="x", name=name)
    db.add(user)
    db.flush()
    group = Group(name=name, created_by=user.id)
    db.add(group)
    db.flush()
    db.add(GroupMembership(user_id=user.id, group_id=group.id, role="admin"))
    db.flush()
    return group


def _commitment(db, group_id, content, status="confirmed"):
    c = Commitment(
        group_id=group_id, content=content, status=status,
        source_type="chat", evidence="근거",
    )
    db.add(c)
    db.flush()
    return c


def test_add_actions_are_safe(db_session):
    group = _seed_group(db_session, "A팀")
    db_session.commit()

    actions, dropped = assistant_service.validate_actions(
        db_session, group.id,
        [{"kind": "todo_add", "content": "시안 정리", "due_date": "2026-08-20"}],
    )

    assert dropped == 0
    assert actions[0]["risk"] == "safe"
    assert actions[0]["payload"] == {"content": "시안 정리", "due_date": "2026-08-20"}
    assert actions[0]["warning"] is None
    assert actions[0]["id"]


def test_delete_and_status_actions_need_confirmation(db_session):
    group = _seed_group(db_session, "A팀")
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
    )

    assert dropped == 0
    assert [a["risk"] for a in actions] == ["confirm", "confirm"]
    # 되돌릴 수 없는 전이에는 경고가 붙는다.
    assert "되돌릴 수 없" in actions[1]["warning"]


def test_todo_done_is_safe_because_it_toggles_back(db_session):
    group = _seed_group(db_session, "A팀")
    todo = Todo(group_id=group.id, content="끝낼 일")
    db_session.add(todo)
    db_session.commit()

    actions, _ = assistant_service.validate_actions(
        db_session, group.id, [{"kind": "todo_done", "todo_id": todo.id}]
    )

    assert actions[0]["risk"] == "safe"


def test_unknown_id_is_dropped(db_session):
    group = _seed_group(db_session, "A팀")
    db_session.commit()

    actions, dropped = assistant_service.validate_actions(
        db_session, group.id, [{"kind": "todo_delete", "todo_id": 99999}]
    )

    assert actions == []
    assert dropped == 1


def test_other_groups_id_is_dropped(db_session):
    """타 그룹 id를 지목하면 버린다 — 통과시키면 남의 데이터를 지운다."""
    group_a = _seed_group(db_session, "A팀")
    group_b = _seed_group(db_session, "B팀")
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
    )

    assert actions == []
    assert dropped == 2


def test_illegal_transition_is_dropped(db_session):
    """proposed -> fulfilled 는 _ALLOWED_TRANSITIONS에 없다."""
    group = _seed_group(db_session, "A팀")
    commitment = _commitment(db_session, group.id, "미확인 약속", status="proposed")
    db_session.commit()

    actions, dropped = assistant_service.validate_actions(
        db_session, group.id,
        [{"kind": "commitment_status", "commitment_id": commitment.id, "to_status": "fulfilled"}],
    )

    assert actions == []
    assert dropped == 1


def test_unknown_kind_is_dropped(db_session):
    group = _seed_group(db_session, "A팀")
    db_session.commit()

    actions, dropped = assistant_service.validate_actions(
        db_session, group.id, [{"kind": "drop_database"}]
    )

    assert actions == []
    assert dropped == 1


def test_add_action_without_content_is_dropped(db_session):
    group = _seed_group(db_session, "A팀")
    db_session.commit()

    actions, dropped = assistant_service.validate_actions(
        db_session, group.id,
        [{"kind": "todo_add", "content": "   "}, {"kind": "schedule_add", "title": "회의"}],
    )

    # 내용이 빈 할 일, 날짜 없는 일정 둘 다 버린다.
    assert actions == []
    assert dropped == 2


def test_validation_does_not_write_to_db(db_session):
    group = _seed_group(db_session, "A팀")
    todo = Todo(group_id=group.id, content="그대로 남을 일")
    db_session.add(todo)
    db_session.commit()

    assistant_service.validate_actions(
        db_session, group.id, [{"kind": "todo_delete", "todo_id": todo.id}]
    )

    assert db_session.get(Todo, todo.id) is not None
