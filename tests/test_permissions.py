import pytest
from fastapi import HTTPException

from models import Group, GroupMembership, User
from permissions import require_group_admin, require_group_member


@pytest.fixture()
def seeded(client, db_session):
    """멤버 1명 + 관리자 1명이 있는 그룹 하나."""
    admin = User(email="a@t.dev", password_hash="x", name="관리자", role="member")
    member = User(email="m@t.dev", password_hash="x", name="멤버", role="member")
    outsider = User(email="o@t.dev", password_hash="x", name="외부", role="member")
    db_session.add_all([admin, member, outsider])
    db_session.flush()
    group = Group(name="A팀", created_by=admin.id)
    db_session.add(group)
    db_session.flush()
    db_session.add_all([
        GroupMembership(user_id=admin.id, group_id=group.id, role="admin"),
        GroupMembership(user_id=member.id, group_id=group.id, role="member"),
    ])
    db_session.commit()
    return {"admin": admin, "member": member, "outsider": outsider, "group": group}


def test_member_passes_member_check(seeded, db_session):
    m = require_group_member(seeded["member"], seeded["group"].id, db_session)
    assert m.role == "member"


def test_outsider_fails_member_check(seeded, db_session):
    with pytest.raises(HTTPException) as exc:
        require_group_member(seeded["outsider"], seeded["group"].id, db_session)
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "GROUP_ACCESS_FORBIDDEN"


def test_member_fails_admin_check(seeded, db_session):
    with pytest.raises(HTTPException) as exc:
        require_group_admin(seeded["member"], seeded["group"].id, db_session)
    assert exc.value.status_code == 403


def test_admin_passes_admin_check(seeded, db_session):
    m = require_group_admin(seeded["admin"], seeded["group"].id, db_session)
    assert m.role == "admin"


def test_admin_check_uses_caller_supplied_error_code(seeded, db_session):
    """엔드포인트마다 프론트가 분기하는 코드가 다르므로 호출부가 지정할 수 있어야 한다."""
    with pytest.raises(HTTPException) as exc:
        require_group_admin(
            seeded["member"], seeded["group"].id, db_session,
            code="GROUP_INVITE_FORBIDDEN", message="관리자만 초대할 수 있습니다.",
        )
    assert exc.value.detail["code"] == "GROUP_INVITE_FORBIDDEN"


def test_nonexistent_group_is_forbidden_not_found(seeded, db_session):
    """없는 그룹에 404를 주면 그룹 id의 존재 여부가 새어나간다."""
    with pytest.raises(HTTPException) as exc:
        require_group_member(seeded["admin"], 99999, db_session)
    assert exc.value.status_code == 403


def test_admin_in_one_group_is_not_admin_in_another(seeded, db_session):
    """이 변경의 존재 이유. 전역 역할이면 이 테스트가 실패한다."""
    other = Group(name="B팀", created_by=seeded["outsider"].id)
    db_session.add(other)
    db_session.flush()
    db_session.add(GroupMembership(user_id=seeded["outsider"].id, group_id=other.id, role="admin"))
    db_session.add(GroupMembership(user_id=seeded["admin"].id, group_id=other.id, role="member"))
    db_session.commit()

    assert require_group_admin(seeded["outsider"], other.id, db_session).role == "admin"
    with pytest.raises(HTTPException):
        require_group_admin(seeded["admin"], other.id, db_session)
