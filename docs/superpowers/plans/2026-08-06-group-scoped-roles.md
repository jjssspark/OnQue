# 그룹별 권한·계정 (A묶음) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 역할을 `User` 전역 속성에서 `GroupMembership` 소속 속성으로 옮겨, 한 사람이 팀마다 다른 역할을 갖게 한다.

**Architecture:** `permissions.py` 하나에 권한 판정을 모으고, 흩어진 16곳의 `current_user.role != "admin"`을 `require_group_member` / `require_group_admin` 호출로 교체한다. 전역 admin이 유일하게 관여하던 "전사 자료"(group_id NULL) 경로는 운영 데이터가 0건이므로 개념째 제거한다. 그룹 생성을 모든 인증 사용자에게 열고 생성자를 그 그룹의 admin으로 만든다.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (`Mapped[T]` + `mapped_column`), pytest, Next.js App Router, Neon Postgres (운영) / SQLite in-memory (테스트)

**스펙:** `docs/superpowers/specs/2026-08-06-group-scoped-roles-design.md`

## Global Constraints

- 모든 `/api/v1` 응답은 봉투 형식. `{"success": bool, "data": ..., "error": ...}`. `data`와 `error` 중 하나는 반드시 `null`.
- 에러는 `HTTPException(status, detail={"code": ..., "message": ...})`. **기존 에러 코드 문자열을 바꾸지 않는다** — 프론트가 `code`로 분기하므로 코드 변경은 깨는 변경이다.
- `main.py:42`에는 `HTTPException` 핸들러만 있다. 다른 예외가 새어나가면 봉투가 아닌 맨 500이 나간다. DB 제약 위반 가능 지점은 반드시 잡는다.
- Alembic이 없다. `Base.metadata.create_all`은 **없는 테이블만** 만들고 ALTER는 하지 않는다. 컬럼 추가는 `scripts/migrate_*.py`가 담당한다.
- 목록 엔드포인트는 페이지네이션 없이 전체를 반환하지 않는다. 기본 `limit=20`, 최대 100.
- 사용자 대면 문자열은 한국어. **이모지를 아이콘으로 쓰지 않는다.**
- 테스트는 `tests/conftest.py`의 `client` / `db_session` 픽스처를 쓴다. 두 픽스처는 같은 in-memory SQLite 엔진을 공유한다.
- SQLite는 `PRAGMA foreign_keys=ON` 없이는 FK를 강제하지 않는다. 이 프로젝트는 켜지 않는다. FK 캐스케이드에 의존하는 동작은 테스트로 검증할 수 없으므로 애플리케이션 코드에서 직접 처리한다.
- 태스크마다 `venv/bin/pytest tests/ -q` 전체를 돌려 모두 통과하는 것을 확인하고 커밋한다.
- 여러 태스크의 테스트가 `_signup(client, email, name)` 헬퍼를 쓴다. 정의는 Task 2에 있다. 헬퍼가 없는 테스트 파일에는 **그 정의를 그대로 복사한다** — 테스트 파일끼리 import하지 않는다.
- 이메일은 파일 안에서 유일해야 한다. `client` 픽스처가 테스트마다 DB를 새로 만들지만, 같은 함수 안에서 같은 이메일로 두 번 가입하면 409가 난다.

---

### Task 1: `GroupMembership.role` 스키마와 `permissions.py`

**Files:**
- Modify: `models.py` — `GroupMembership` 클래스
- Create: `permissions.py`
- Modify: `main.py:90-96` — `_require_group_member` 제거하고 import로 교체
- Create: `scripts/migrate_group_roles.py`
- Test: `tests/test_permissions.py`

**Interfaces:**
- Produces: `GROUP_ROLES = ("admin", "member")` (models.py), `require_group_member(user, group_id, db) -> GroupMembership`, `require_group_admin(user, group_id, db, *, code, message) -> GroupMembership` (permissions.py)
- Consumes: 없음 (첫 태스크)

인자 순서 `(user, group_id, db)`는 기존 `main.py:90`의 `_require_group_member`와 같다. 호출부를 그대로 옮기기 위해서다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_permissions.py`:

```python
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
```

- [ ] **Step 2: 실패를 확인한다**

Run: `venv/bin/pytest tests/test_permissions.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'permissions'`

- [ ] **Step 3: `models.py`에 role을 추가한다**

`GroupMembership` 클래스를 이렇게 바꾼다.

```python
GROUP_ROLES = ("admin", "member")


class GroupMembership(Base):
    __tablename__ = "group_memberships"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "group_id"),
        CheckConstraint(f"role IN {GROUP_ROLES}", name="ck_group_memberships_role"),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"))
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default="member")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

`GROUP_ROLES`는 `DOCUMENT_CATEGORIES`·`COMMITMENT_STATUSES`와 같은 자리(파일 상단 상수 구역)에 둔다.

`server_default="member"`인 이유: 마이그레이션에서 기존 행을 채우고, 코드가 role을 빠뜨려도 유효한 값이 들어간다.

- [ ] **Step 4: `permissions.py`를 만든다**

```python
"""그룹 단위 권한 판정.

권한 검사가 라우터마다 흩어져 있으면 한 곳을 빠뜨렸을 때 조용히 뚫린다.
여기 모아 두면 판정 자체를 테스트할 수 있다.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import GroupMembership, User


def require_group_member(user: User, group_id: int, db: Session) -> GroupMembership:
    membership = db.get(GroupMembership, {"user_id": user.id, "group_id": group_id})
    if not membership:
        # 그룹이 아예 없는 경우도 여기로 온다. 404로 나누면 비멤버에게
        # 그룹 id의 존재 여부가 새어나간다.
        raise HTTPException(
            status_code=403,
            detail={"code": "GROUP_ACCESS_FORBIDDEN", "message": "해당 그룹에 소속되어 있지 않습니다."},
        )
    return membership


def require_group_admin(
    user: User,
    group_id: int,
    db: Session,
    *,
    code: str = "GROUP_ACCESS_FORBIDDEN",
    message: str = "이 팀의 관리자만 가능한 작업입니다.",
) -> GroupMembership:
    """엔드포인트마다 프론트가 분기하는 에러 코드가 다르므로 호출부가 지정한다."""
    membership = require_group_member(user, group_id, db)
    if membership.role != "admin":
        raise HTTPException(status_code=403, detail={"code": code, "message": message})
    return membership
```

- [ ] **Step 5: `main.py`의 로컬 헬퍼를 제거한다**

`main.py:90-96`의 `def _require_group_member(...)` 정의를 지우고, import 구역에 추가한다.

```python
from permissions import require_group_admin, require_group_member
```

`main.py` 안의 `_require_group_member(` 호출을 전부 `require_group_member(`로 바꾼다. 인자 순서는 같으므로 이름만 바뀐다.

- [ ] **Step 6: 테스트를 돌려 통과를 확인한다**

Run: `venv/bin/pytest tests/test_permissions.py -q`
Expected: PASS (7개)

Run: `venv/bin/pytest tests/ -q`
Expected: 전체 통과. `server_default`는 SQLAlchemy가 INSERT에 컬럼을 넣지 않을 때만 적용되므로, 기존 `GroupMembership(...)` 생성부에 role이 없어도 통과해야 한다. 통과하지 않으면 그 호출부를 보고한다.

- [ ] **Step 7: 마이그레이션 스크립트를 만든다**

`scripts/migrate_group_roles.py`:

```python
"""그룹별 역할 마이그레이션.

실행 순서 (반드시 이 순서로):
1. 이 스크립트를 먼저 실행한다.
2. 그 다음에 새 코드를 배포한다.

순서가 중요한 이유: 새 코드를 먼저 배포하면 SQLAlchemy가 매핑된 모든 컬럼을
SELECT에 담기 때문에, DB에 role 컬럼이 없는 동안 group_memberships를 건드리는
모든 쿼리가 실패한다 — 그룹·채팅·문서 전체가 죽는다. TS-016과 같은 실패 모드다.
반대로 컬럼 추가는 구버전 코드에 무해하다 — 모르는 컬럼은 그냥 무시한다.
"""

from sqlalchemy import text

from db import engine


def _column_exists(conn, table: str, column: str) -> bool:
    result = conn.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = :column"
        ),
        {"table": table, "column": column},
    )
    return result.first() is not None


def main() -> None:
    with engine.begin() as conn:
        if not _column_exists(conn, "group_memberships", "role"):
            conn.execute(
                text(
                    "ALTER TABLE group_memberships "
                    "ADD COLUMN role TEXT NOT NULL DEFAULT 'member'"
                )
            )
            # 이 UPDATE는 멱등하지 않다 — 컬럼을 막 추가한 이 분기 안에서만
            # 실행돼야 한다. 재실행 경로에서 돌리면 그 사이 사람이 바꾼
            # 역할을 '그룹 생성자만 관리자'로 되돌려 버린다.
            updated = conn.execute(
                text(
                    "UPDATE group_memberships SET role = 'admin' "
                    "WHERE (user_id, group_id) IN "
                    "(SELECT created_by, id FROM groups)"
                )
            ).rowcount
            print(f"group_memberships.role 추가 + 그룹 생성자 {updated}명을 admin으로")
        else:
            print("group_memberships.role 이미 있음")

        if not _column_exists(conn, "announcements", "group_id"):
            remaining = conn.execute(text("SELECT COUNT(*) FROM announcements")).scalar()
            if remaining:
                # NOT NULL 컬럼을 기존 행이 있는 테이블에 붙일 수 없다.
                # 어느 그룹의 공지인지 추측하지 않는다 — 사람이 정해야 한다.
                raise SystemExit(
                    f"announcements에 {remaining}행이 있다. group_id를 수동으로 정하고 다시 실행하라."
                )
            conn.execute(
                text(
                    "ALTER TABLE announcements ADD COLUMN group_id INTEGER "
                    "NOT NULL REFERENCES groups(id)"
                )
            )
            print("announcements.group_id 추가 (0행이라 백필 없음)")
        else:
            print("announcements.group_id 이미 있음")


if __name__ == "__main__":
    main()
```

`announcements.group_id`는 Task 5에서 모델에 반영하지만, 마이그레이션은 한 스크립트로 묶는다. 배포는 한 번이고 스크립트를 두 번 돌릴 이유가 없다.

- [ ] **Step 8: 커밋**

```bash
git add models.py permissions.py main.py scripts/migrate_group_roles.py tests/test_permissions.py
git commit -m "feat: 그룹 멤버십에 역할을 두고 권한 판정을 permissions.py로 모음"
```

---

### Task 2: 그룹 생성 개방과 생성자 관리자 지정

**Files:**
- Modify: `routers/groups.py` — `_require_admin` 제거, `create_group`, `join_group`
- Modify: `routers/auth.py` — `signup`의 `is_first_user` 분기 제거, `_serialize_user`
- Test: `tests/test_group_routes.py`, `tests/test_auth_routes.py`

**Interfaces:**
- Consumes: Task 1의 `GroupMembership.role`
- Produces: 인증된 모든 사용자가 `POST /api/v1/groups`를 호출할 수 있다. 응답의 `user` 객체에서 `role` 키가 사라진다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_group_routes.py`에 추가:

```python
def _signup(client, email, name):
    res = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "password123", "name": name},
    )
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['data']['token']}"}


def test_any_user_can_create_a_group_and_becomes_its_admin(client):
    _signup(client, "first@t.dev", "첫째")          # 예전이라면 이 사람만 admin
    headers = _signup(client, "second@t.dev", "둘째")

    res = client.post("/api/v1/groups", json={"name": "둘째팀"}, headers=headers)
    assert res.status_code == 200
    group_id = res.json()["data"]["id"]

    me = client.get("/api/v1/me", headers=headers).json()["data"]
    assert [g["role"] for g in me["groups"] if g["id"] == group_id] == ["admin"]


def test_group_creation_is_atomic(client, db_session):
    """그룹만 남고 멤버십이 없으면 만든 사람도 자기 그룹에 못 들어간다."""
    from models import ChatRoomMember, Group, GroupMembership

    headers = _signup(client, "solo@t.dev", "혼자")
    group_id = client.post(
        "/api/v1/groups", json={"name": "혼자팀"}, headers=headers
    ).json()["data"]["id"]

    assert db_session.get(Group, group_id) is not None
    memberships = db_session.query(GroupMembership).filter_by(group_id=group_id).all()
    assert len(memberships) == 1 and memberships[0].role == "admin"
    # 기본 방에도 들어가 있어야 채팅 화면이 빈 목록이 아니다
    assert db_session.query(ChatRoomMember).count() == 1


def test_new_user_starts_with_no_groups(client):
    """가입 직후 소속 그룹이 없어야 프론트가 팀 만들기 폼을 띄운다."""
    headers = _signup(client, "fresh@t.dev", "신규")
    assert client.get("/api/v1/me", headers=headers).json()["data"]["groups"] == []


def test_invited_member_joins_as_member_not_admin(client):
    admin_headers = _signup(client, "owner@t.dev", "주인")
    group_id = client.post(
        "/api/v1/groups", json={"name": "A팀"}, headers=admin_headers
    ).json()["data"]["id"]

    client.post(
        f"/api/v1/groups/{group_id}/invitations",
        json={"email": "guest@t.dev"},
        headers=admin_headers,
    )
    guest_headers = _signup(client, "guest@t.dev", "손님")

    me = client.get("/api/v1/me", headers=guest_headers).json()["data"]
    assert [g["role"] for g in me["groups"]] == ["member"]
```

`tests/test_auth_routes.py`에 추가:

```python
def test_signup_response_no_longer_exposes_global_role(client):
    """역할은 그룹 소속 속성이 됐다. 사용자 객체에 role이 남아 있으면
    프론트가 계속 그걸 읽어 잘못된 관리자 UI를 띄운다."""
    res = client.post(
        "/api/v1/auth/signup",
        json={"email": "norole@t.dev", "password": "password123", "name": "역할없음"},
    )
    assert "role" not in res.json()["data"]["user"]
```

- [ ] **Step 2: 실패를 확인한다**

Run: `venv/bin/pytest tests/test_group_routes.py tests/test_auth_routes.py -q`
Expected: FAIL — 둘째 사용자의 그룹 생성이 403 `GROUP_CREATE_FORBIDDEN`

- [ ] **Step 3: `routers/groups.py`를 고친다**

`_require_admin` 함수(`routers/groups.py:23-28`)를 통째로 삭제한다.

`join_group`의 멤버십 생성에 역할을 명시한다.

```python
    db.add(GroupMembership(user_id=user_id, group_id=group_id, role="member"))
```

`create_group`을 한 트랜잭션으로 바꾼다.

```python
@router.post("/groups")
def create_group(
    body: GroupCreateBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """인증된 사용자면 누구나 팀을 만들 수 있고, 만든 사람이 그 팀의 관리자가 된다.

    그룹·멤버십·기본 방을 한 트랜잭션에서 만든다. 나눠 커밋하면 중간에
    실패했을 때 멤버십 없는 고아 그룹이 남고, 만든 사람조차 접근할 수 없다.
    """
    group = Group(name=body.name, created_by=current_user.id)
    db.add(group)
    db.flush()
    db.add(GroupMembership(user_id=current_user.id, group_id=group.id, role="admin"))
    room = ChatRoom(
        group_id=group.id, name=DEFAULT_CHAT_ROOM_NAME, created_by=current_user.id
    )
    db.add(room)
    db.flush()
    db.add(ChatRoomMember(room_id=room.id, user_id=current_user.id))
    db.commit()
    db.refresh(group)
    return {"success": True, "data": {"id": group.id, "name": group.name}, "error": None}
```

- [ ] **Step 4: `routers/auth.py`를 고친다**

`_serialize_user`에서 `role`을 뺀다.

```python
def _serialize_user(user: User) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name}
```

`signup`에서 `is_first_user` 계산과 기본 그룹 생성 블록(`routers/auth.py:50-75`)을 지운다. `User(...)` 생성은 이렇게 남는다.

```python
    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        name=body.name,
        role="member",
    )
```

`User.role`은 컬럼이 아직 NOT NULL이므로 값을 넣어야 한다. **어떤 코드도 이 값을 읽지 않는다.** 컬럼 제거는 신코드 안정화 후 별도 작업이다.

`ChatRoom`·`ChatRoomMember`·`Group`·`GroupMembership` import가 이 파일에서 더 이상 쓰이지 않으면 지운다. `DEFAULT_CHAT_ROOM_NAME`, `DEFAULT_GROUP_NAME`도 같다. 사용처가 남아 있으면 그대로 둔다.

- [ ] **Step 5: 테스트 전체를 돌린다**

Run: `venv/bin/pytest tests/ -q`

기본 그룹 자동 생성에 기대던 기존 테스트가 깨진다. 그런 테스트는 **명시적으로 `POST /api/v1/groups`를 호출하도록** 고친다. 단언을 느슨하게 만들어 통과시키지 않는다.

- [ ] **Step 6: 커밋**

```bash
git add routers/groups.py routers/auth.py tests/
git commit -m "feat: 누구나 팀을 만들고 만든 사람이 그 팀의 관리자가 된다"
```

---

### Task 3: `routers/groups.py`의 나머지 권한 지점 교체

**Files:**
- Modify: `routers/groups.py` — 6곳
- Test: `tests/test_group_routes.py`, `tests/test_group_invitations.py`

**Interfaces:**
- Consumes: `permissions.require_group_member`, `permissions.require_group_admin`
- Produces: `GET /groups/{id}/members` 응답의 `role`이 **멤버십 역할**이 된다 (필드명은 그대로)

**권한 먼저, 존재 확인 나중.** 그룹 404를 권한 검사보다 앞에 두면 비멤버가 그룹 id의 존재 여부를 알아낼 수 있다. 기존 코드는 일부 지점에서 404를 먼저 냈으므로, 그런 테스트는 403 기대로 바꾸고 이유를 주석에 남긴다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_group_routes.py`에 추가:

```python
def test_member_list_returns_membership_role_not_user_role(client):
    """필드명이 role 그대로라 값의 의미가 조용히 바뀐다. 테스트로 고정한다."""
    owner = _signup(client, "own@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    client.post(f"/api/v1/groups/{gid}/invitations", json={"email": "mem@t.dev"}, headers=owner)
    _signup(client, "mem@t.dev", "멤버")

    rows = client.get(f"/api/v1/groups/{gid}/members", headers=owner).json()["data"]
    assert {r["email"]: r["role"] for r in rows} == {"own@t.dev": "admin", "mem@t.dev": "member"}


def test_member_cannot_invite(client):
    owner = _signup(client, "own2@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    client.post(f"/api/v1/groups/{gid}/invitations", json={"email": "mem2@t.dev"}, headers=owner)
    member = _signup(client, "mem2@t.dev", "멤버")

    res = client.post(
        f"/api/v1/groups/{gid}/invitations", json={"email": "x@t.dev"}, headers=member
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "GROUP_INVITE_FORBIDDEN"


def test_member_can_see_pending_invitations(client):
    """초대는 못 하지만 누가 대기 중인지는 볼 수 있다 — 기존 동작."""
    owner = _signup(client, "own3@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    client.post(f"/api/v1/groups/{gid}/invitations", json={"email": "mem3@t.dev"}, headers=owner)
    member = _signup(client, "mem3@t.dev", "멤버")

    assert client.get(f"/api/v1/groups/{gid}/invitations", headers=member).status_code == 200


def test_outsider_gets_403_not_404_for_unknown_group(client):
    """404로 나누면 그룹 id의 존재 여부가 새어나간다."""
    headers = _signup(client, "out@t.dev", "외부")
    assert client.get("/api/v1/groups/99999/members", headers=headers).status_code == 403


def test_cannot_remove_the_last_admin(client):
    """전역 admin이 사라졌으므로, 마지막 관리자가 빠지면 그 팀은 아무도
    초대할 수 없는 복구 불가 상태가 된다."""
    owner = _signup(client, "last@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    me = client.get("/api/v1/me", headers=owner).json()["data"]["user"]

    res = client.delete(f"/api/v1/groups/{gid}/members/{me['id']}", headers=owner)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "GROUP_LAST_ADMIN"
```

- [ ] **Step 2: 실패를 확인한다**

Run: `venv/bin/pytest tests/test_group_routes.py -q`
Expected: FAIL — 멤버 목록의 role이 `User.role` 값으로 나오고, 마지막 관리자 제거가 200

- [ ] **Step 3: 6곳을 교체한다**

파일 상단에 추가:

```python
from permissions import require_group_admin, require_group_member
```

**`list_group_members`** — `routers/groups.py:113-127`의 404 검사와 role 분기를 이걸로 대체한다.

```python
    require_group_member(current_user, group_id, db)
```

그리고 직렬화를 멤버십 역할로 바꾼다.

```python
    memberships = db.scalars(
        select(GroupMembership).where(GroupMembership.group_id == group_id)
    ).all()
    role_by_user = {m.user_id: m.role for m in memberships}
    users = (
        db.scalars(select(User).where(User.id.in_(role_by_user))).all()
        if role_by_user
        else []
    )
    return {
        "success": True,
        "data": [
            {"id": u.id, "email": u.email, "name": u.name, "role": role_by_user[u.id]}
            for u in users
        ],
        "error": None,
    }
```

**`add_group_member`** — `routers/groups.py:152-161`의 role 검사와 그룹 404를 대체한다.

```python
    require_group_admin(
        current_user, group_id, db,
        code="GROUP_MEMBER_ADD_FORBIDDEN", message="관리자만 가능한 작업입니다.",
    )
```

대상 사용자 404 검사는 그대로 둔다.

**`invite_to_group_by_email`** — `routers/groups.py:210-218`을 대체한다.

```python
    require_group_admin(
        current_user, group_id, db,
        code="GROUP_INVITE_FORBIDDEN", message="관리자만 초대할 수 있습니다.",
    )
```

**`list_group_invitations`** — `routers/groups.py:277-287`을 대체한다.

```python
    require_group_member(current_user, group_id, db)
```

**`cancel_group_invitation`** — `routers/groups.py:311-315`를 대체한다.

```python
    require_group_admin(
        current_user, group_id, db,
        code="GROUP_INVITE_FORBIDDEN", message="관리자만 초대를 취소할 수 있습니다.",
    )
```

**`remove_group_member`** — `routers/groups.py:334-338`을 대체하고, 마지막 관리자 보호를 추가한다.

```python
    require_group_admin(
        current_user, group_id, db,
        code="GROUP_MEMBER_ADD_FORBIDDEN", message="관리자만 가능한 작업입니다.",
    )
    membership = db.get(GroupMembership, {"user_id": user_id, "group_id": group_id})
    if membership and membership.role == "admin":
        admin_count = db.scalar(
            select(func.count())
            .select_from(GroupMembership)
            .where(GroupMembership.group_id == group_id, GroupMembership.role == "admin")
        )
        if admin_count <= 1:
            # 전역 admin이 없어졌으므로 관리자가 0명이 되면 아무도 초대할 수
            # 없고 밖에서 고쳐줄 사람도 없다.
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "GROUP_LAST_ADMIN",
                    "message": "팀의 마지막 관리자는 내보낼 수 없습니다.",
                },
            )
    if membership:
        # ... 기존 삭제 로직 그대로 (멤버십 삭제 + 그 그룹 방들의 ChatRoomMember 정리) ...
```

`func`는 이미 `routers/groups.py:5`에서 import되어 있다.

- [ ] **Step 4: 테스트를 돌린다**

Run: `venv/bin/pytest tests/ -q`

404를 기대하던 기존 테스트가 403으로 바뀐다. 바꾸되 **왜 403인지 주석을 남긴다.**

- [ ] **Step 5: 커밋**

```bash
git add routers/groups.py tests/
git commit -m "feat: 그룹 라우터 권한을 그룹 역할 기준으로 교체하고 마지막 관리자를 보호"
```

---

### Task 4: `main.py` 권한 교체와 전사 자료 경로 제거

**Files:**
- Modify: `main.py` — `delete_document`, `create_schedule`, `update_schedule`, `delete_schedule`, `delete_chat_room`, `remove_room_member`, `ScheduleCreate`
- Test: `tests/test_group_scoping.py`, `tests/test_chat_rooms.py`

**Interfaces:**
- Consumes: `permissions.require_group_admin`
- Produces: `POST /schedules`가 `group_id`를 필수로 받는다 (없으면 422)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_group_scoping.py`에 추가 (`_signup` 헬퍼가 없으면 Task 2의 것을 그대로 복사한다):

```python
def test_schedule_requires_a_group(client):
    """전사 일정 개념을 없앴다. group_id 없이 만들 수 없다."""
    headers = _signup(client, "sch@t.dev", "일정")
    res = client.post(
        "/schedules", json={"title": "회의", "scheduled_date": "2026-09-01"}, headers=headers
    )
    assert res.status_code == 422


def test_group_member_can_delete_group_document(client, db_session):
    """현재 동작 유지 — 작성자 컬럼이 없어 '본인 것만'을 구현할 수 없다."""
    from models import Document

    owner = _signup(client, "d1@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    client.post(f"/api/v1/groups/{gid}/invitations", json={"email": "d2@t.dev"}, headers=owner)
    member = _signup(client, "d2@t.dev", "멤버")

    doc = Document(
        group_id=gid, source_type="document", category="기타",
        filename="a.txt", summary="요약",
    )
    db_session.add(doc)
    db_session.commit()

    assert client.delete(f"/documents/{doc.id}", headers=member).status_code == 200


def test_groupless_document_cannot_be_deleted_by_anyone(client, db_session):
    """전역 admin이 사라져 이 문서를 지울 주체가 없다. 운영에 0건이지만 방어한다."""
    from models import Document

    headers = _signup(client, "d3@t.dev", "누구")
    doc = Document(
        group_id=None, source_type="document", category="기타",
        filename="orphan.txt", summary="요약",
    )
    db_session.add(doc)
    db_session.commit()

    res = client.delete(f"/documents/{doc.id}", headers=headers)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "DOCUMENT_DELETE_FORBIDDEN"
```

`tests/test_chat_rooms.py`에 추가:

```python
def _user_id(client, headers) -> int:
    return client.get("/api/v1/me", headers=headers).json()["data"]["user"]["id"]


def test_group_admin_can_delete_someone_elses_room(client):
    owner = _signup(client, "r1@t.dev", "관리자")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    client.post(f"/api/v1/groups/{gid}/invitations", json={"email": "r2@t.dev"}, headers=owner)
    member = _signup(client, "r2@t.dev", "멤버")

    room_id = client.post(
        "/chat/rooms", json={"group_id": gid, "name": "멤버방"}, headers=member
    ).json()["id"]

    assert client.delete(f"/chat/rooms/{room_id}", headers=owner).status_code == 200


def test_plain_member_cannot_delete_someone_elses_room(client):
    owner = _signup(client, "r3@t.dev", "관리자")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    for email in ("r4@t.dev", "r5@t.dev"):
        client.post(f"/api/v1/groups/{gid}/invitations", json={"email": email}, headers=owner)
    a = _signup(client, "r4@t.dev", "A")
    b = _signup(client, "r5@t.dev", "B")

    room_id = client.post(
        "/chat/rooms", json={"group_id": gid, "name": "A방"}, headers=a
    ).json()["id"]
    client.post(
        f"/chat/rooms/{room_id}/members", json={"user_id": _user_id(client, b)}, headers=a
    )

    res = client.delete(f"/chat/rooms/{room_id}", headers=b)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "CHAT_ROOM_DELETE_FORBIDDEN"
```

- [ ] **Step 2: 실패를 확인한다**

Run: `venv/bin/pytest tests/test_group_scoping.py tests/test_chat_rooms.py -q`
Expected: FAIL — group_id 없는 일정이 200으로 생성되고, 그룹 관리자의 남의 방 삭제가 403

- [ ] **Step 3: 문서·일정에서 전사 경로를 제거한다**

`delete_document`(`main.py:293-300`)의 분기를 이렇게 바꾼다.

```python
    if doc.group_id is None:
        # 전사 문서 개념을 없앴다. 지울 주체가 정의되지 않는다.
        raise HTTPException(
            status_code=403,
            detail={
                "code": "DOCUMENT_DELETE_FORBIDDEN",
                "message": "팀에 속하지 않은 문서는 삭제할 수 없습니다.",
            },
        )
    require_group_member(current_user, doc.group_id, db)
```

`ScheduleCreate`의 `group_id`를 `int | None = None`에서 `int`(필수)로 바꾼다.

`create_schedule`(`main.py:436-441`):

```python
    require_group_member(current_user, body.group_id, db)
```

`update_schedule`(`main.py:481-487`)과 `delete_schedule`(`main.py:509-515`):

```python
    if schedule.group_id is None:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "SCHEDULE_EDIT_FORBIDDEN",
                "message": "팀에 속하지 않은 일정은 수정할 수 없습니다.",
            },
        )
    require_group_member(current_user, schedule.group_id, db)
```

- [ ] **Step 4: 채팅방 두 곳을 교체한다**

`delete_chat_room`(`main.py:676-683`):

```python
    if room.created_by != current_user.id:
        require_group_admin(
            current_user, room.group_id, db,
            code="CHAT_ROOM_DELETE_FORBIDDEN",
            message="방을 만든 사람이나 팀 관리자만 삭제할 수 있습니다.",
        )
```

`remove_room_member`(`main.py:783-793`):

```python
    if user_id != current_user.id and room.created_by != current_user.id:
        require_group_admin(
            current_user, room.group_id, db,
            code="CHAT_ROOM_MEMBER_REMOVE_FORBIDDEN",
            message="방을 만든 사람이나 팀 관리자만 다른 사람을 내보낼 수 있습니다.",
        )
```

`_require_room_access`가 이미 방 소속을 확인하므로 `room.group_id`는 신뢰할 수 있다.

- [ ] **Step 5: 테스트를 돌린다**

Run: `venv/bin/pytest tests/ -q`

`group_id` 없이 일정을 만들던 기존 테스트는 그룹을 만들어 넘기도록 고친다.

- [ ] **Step 6: 커밋**

```bash
git add main.py tests/
git commit -m "feat: 문서·일정·채팅방 권한을 그룹 역할 기준으로 바꾸고 전사 자료 경로 제거"
```

---

### Task 5: 공지를 팀 단위로

**Files:**
- Modify: `models.py` — `Announcement`
- Modify: `routers/announcements.py`
- Test: `tests/test_announcement_routes.py`

**Interfaces:**
- Consumes: `permissions.require_group_admin`
- Produces: `GET /api/v1/announcements?group_id=<int>&limit=<int>`, `POST /api/v1/announcements` 본문에 `group_id` 추가. 응답에 `meta`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_announcement_routes.py`에 추가:

```python
def test_announcement_is_scoped_to_its_group(client):
    a = _signup(client, "ga@t.dev", "A관리자")
    b = _signup(client, "gb@t.dev", "B관리자")
    gid_a = client.post("/api/v1/groups", json={"name": "A팀"}, headers=a).json()["data"]["id"]
    gid_b = client.post("/api/v1/groups", json={"name": "B팀"}, headers=b).json()["data"]["id"]

    client.post(
        "/api/v1/announcements",
        json={"group_id": gid_a, "title": "A팀 공지", "content": "내용"},
        headers=a,
    )

    assert len(client.get(f"/api/v1/announcements?group_id={gid_a}", headers=a).json()["data"]) == 1
    assert client.get(f"/api/v1/announcements?group_id={gid_b}", headers=b).json()["data"] == []
    # 남의 팀 공지는 조회 자체가 막힌다
    assert client.get(f"/api/v1/announcements?group_id={gid_a}", headers=b).status_code == 403


def test_member_cannot_write_announcement(client):
    owner = _signup(client, "gc@t.dev", "관리자")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    client.post(f"/api/v1/groups/{gid}/invitations", json={"email": "gd@t.dev"}, headers=owner)
    member = _signup(client, "gd@t.dev", "멤버")

    res = client.post(
        "/api/v1/announcements",
        json={"group_id": gid, "title": "몰래", "content": "내용"},
        headers=member,
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "ANNOUNCEMENT_CREATE_FORBIDDEN"


def test_announcement_list_is_paginated(client):
    owner = _signup(client, "ge@t.dev", "관리자")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    for i in range(25):
        client.post(
            "/api/v1/announcements",
            json={"group_id": gid, "title": f"공지{i}", "content": "내용"},
            headers=owner,
        )

    body = client.get(f"/api/v1/announcements?group_id={gid}", headers=owner).json()
    assert len(body["data"]) == 20
    assert body["meta"] == {"total": 25, "limit": 20, "hasNext": True}
```

- [ ] **Step 2: 실패를 확인한다**

Run: `venv/bin/pytest tests/test_announcement_routes.py -q`
Expected: FAIL — `group_id`가 알 수 없는 쿼리 파라미터로 무시되고 전체 공지가 반환된다

- [ ] **Step 3: 모델에 group_id를 추가한다**

```python
class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    ...
```

- [ ] **Step 4: 라우터를 고친다**

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from permissions import require_group_admin, require_group_member


class AnnouncementCreateBody(BaseModel):
    group_id: int
    title: str
    content: str


def _serialize(a: Announcement) -> dict:
    return {
        "id": a.id,
        "group_id": a.group_id,
        "title": a.title,
        "content": a.content,
        "author_id": a.author_id,
        "created_at": a.created_at.isoformat(),
    }


@router.get("/announcements")
def list_announcements(
    group_id: int,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_group_member(current_user, group_id, db)
    total = db.scalar(
        select(func.count()).select_from(Announcement).where(Announcement.group_id == group_id)
    )
    items = db.scalars(
        select(Announcement)
        .where(Announcement.group_id == group_id)
        .order_by(Announcement.created_at.desc())
        .limit(limit)
    ).all()
    return {
        "success": True,
        "data": [_serialize(a) for a in items],
        "error": None,
        "meta": {"total": total, "limit": limit, "hasNext": total > len(items)},
    }


@router.post("/announcements")
def create_announcement(
    body: AnnouncementCreateBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_group_admin(
        current_user, body.group_id, db,
        code="ANNOUNCEMENT_CREATE_FORBIDDEN",
        message="팀 관리자만 공지를 작성할 수 있습니다.",
    )
    announcement = Announcement(
        group_id=body.group_id,
        title=body.title,
        content=body.content,
        author_id=current_user.id,
    )
    db.add(announcement)
    db.commit()
    db.refresh(announcement)
    return {"success": True, "data": _serialize(announcement), "error": None}
```

`HTTPException` import가 더 이상 쓰이지 않으면 지운다.

- [ ] **Step 5: 테스트를 돌린다**

Run: `venv/bin/pytest tests/ -q`

- [ ] **Step 6: 커밋**

```bash
git add models.py routers/announcements.py tests/
git commit -m "feat: 전사 공지를 팀 공지로 바꾸고 페이지네이션 추가"
```

---

### Task 6: 프로필 API 확장과 `GET /users` 제거

**Files:**
- Modify: `routers/auth.py` — `get_me` 확장, `PATCH /me`, `POST /me/password` 추가
- Delete: `routers/users.py`, `tests/test_user_routes.py`
- Modify: `main.py` — `users` 라우터 등록 제거
- Test: `tests/test_auth_routes.py`

**Interfaces:**
- Produces: `GET /api/v1/me` 응답의 각 그룹에 `role`, `user`에 `created_at` 추가. `PATCH /api/v1/me`, `POST /api/v1/me/password`

**기존 응답 모양을 유지한다.** `GET /me`는 이미 `{"user": {...}, "groups": [...]}`를 내려보내고 프론트가 그 모양을 읽는다. 키를 늘리기만 하고 구조는 바꾸지 않는다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
def test_me_reports_role_per_group(client):
    a = _signup(client, "p1@t.dev", "A")
    b = _signup(client, "p2@t.dev", "B")
    gid_b = client.post("/api/v1/groups", json={"name": "B팀"}, headers=b).json()["data"]["id"]
    # p1은 이미 가입돼 있으므로 초대 즉시 합류한다
    client.post(f"/api/v1/groups/{gid_b}/invitations", json={"email": "p1@t.dev"}, headers=b)
    gid_a = client.post("/api/v1/groups", json={"name": "A팀"}, headers=a).json()["data"]["id"]

    groups = client.get("/api/v1/me", headers=a).json()["data"]["groups"]
    assert {g["id"]: g["role"] for g in groups} == {gid_a: "admin", gid_b: "member"}


def test_me_includes_created_at(client):
    headers = _signup(client, "p3@t.dev", "C")
    assert "created_at" in client.get("/api/v1/me", headers=headers).json()["data"]["user"]


def test_can_change_my_name(client):
    headers = _signup(client, "p4@t.dev", "옛이름")
    assert client.patch("/api/v1/me", json={"name": "새이름"}, headers=headers).status_code == 200
    assert client.get("/api/v1/me", headers=headers).json()["data"]["user"]["name"] == "새이름"


def test_password_change_requires_the_current_password(client):
    """현재 비밀번호를 확인하지 않으면 탈취된 토큰이 곧 계정 탈취다."""
    headers = _signup(client, "p5@t.dev", "D")
    res = client.post(
        "/api/v1/me/password",
        json={"current_password": "wrongpassword", "new_password": "newpassword123"},
        headers=headers,
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "USER_PASSWORD_INVALID"


def test_password_change_succeeds_and_old_password_stops_working(client):
    headers = _signup(client, "p6@t.dev", "E")
    assert client.post(
        "/api/v1/me/password",
        json={"current_password": "password123", "new_password": "newpassword123"},
        headers=headers,
    ).status_code == 200

    assert client.post(
        "/api/v1/auth/login", json={"email": "p6@t.dev", "password": "password123"}
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/login", json={"email": "p6@t.dev", "password": "newpassword123"}
    ).status_code == 200


def test_global_user_list_endpoint_is_gone(client):
    """다른 조직 사용자의 이메일이 새어나가는 구멍이었고 쓰는 화면도 없었다."""
    headers = _signup(client, "p7@t.dev", "F")
    assert client.get("/api/v1/users", headers=headers).status_code == 404
```

- [ ] **Step 2: 실패를 확인한다**

Run: `venv/bin/pytest tests/test_auth_routes.py -q`
Expected: FAIL — `groups`에 `role` 키가 없고, `PATCH /me`가 405

- [ ] **Step 3: `get_me`를 확장한다**

```python
@router.get("/me")
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Group.id, Group.name, GroupMembership.role)
        .join(GroupMembership, GroupMembership.group_id == Group.id)
        .where(GroupMembership.user_id == current_user.id)
        .order_by(Group.id)
    ).all()

    return {
        "success": True,
        "data": {
            "user": {
                **_serialize_user(current_user),
                "created_at": current_user.created_at.isoformat(),
            },
            "groups": [{"id": gid, "name": name, "role": role} for gid, name, role in rows],
        },
        "error": None,
    }
```

`get_user_groups` import가 이 파일에서 더 이상 쓰이지 않으면 지운다. 다른 곳에서 쓰면 그대로 둔다.

- [ ] **Step 4: 프로필 수정 엔드포인트를 추가한다**

```python
class ProfileUpdateBody(BaseModel):
    name: str = Field(min_length=1)


class PasswordChangeBody(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


@router.patch("/me")
def update_me(
    body: ProfileUpdateBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.name = body.name
    db.commit()
    db.refresh(current_user)
    return {"success": True, "data": _serialize_user(current_user), "error": None}


@router.post("/me/password")
def change_my_password(
    body: PasswordChangeBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """현재 비밀번호를 반드시 확인한다. 토큰만으로 바꿀 수 있으면
    탈취된 토큰이 그대로 계정 탈취가 된다."""
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=400,
            detail={"code": "USER_PASSWORD_INVALID", "message": "현재 비밀번호가 올바르지 않습니다."},
        )
    current_user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"success": True, "data": {"changed": True}, "error": None}
```

- [ ] **Step 5: `GET /users`를 제거한다**

- `routers/users.py` 삭제
- `main.py`에서 `users` 라우터 import와 `app.include_router(users.router)` 삭제
- `tests/test_user_routes.py` 삭제
- 다른 모듈이 `routers.users.serialize_user`를 import하는지 grep으로 확인하고, 있으면 그 자리에 인라인한다

- [ ] **Step 6: 테스트를 돌린다**

Run: `venv/bin/pytest tests/ -q`

- [ ] **Step 7: 커밋**

```bash
git add routers/ main.py tests/
git commit -m "feat: 프로필 조회·수정·비밀번호 변경 추가, 전체 사용자 목록 엔드포인트 제거"
```

---

### Task 7: 프론트엔드 — API 계층과 그룹 페이지

**Files:**
- Modify: `onque-frontend/lib/api.ts`
- Modify: `onque-frontend/app/groups/page.tsx`
- Read first: `onque-frontend/components/AuthContext.tsx`, `onque-frontend/components/WorkspaceContext.tsx`

**Interfaces:**
- Consumes: Task 2·3·6의 엔드포인트
- Produces: 그룹 타입에 `role: 'admin' | 'member'`

- [ ] **Step 1: `lib/api.ts`를 고친다**

- 그룹 요약 타입에 `role: 'admin' | 'member'`를 추가한다
- `/api/v1/users`를 호출하는 함수(`lib/api.ts:341`)와 그 타입을 삭제한다
- 추가한다:

```ts
export async function createGroup(name: string) {
  return requestEnveloped<{ id: number; name: string }>('/api/v1/groups', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

export async function updateMyName(name: string) {
  return requestEnveloped('/api/v1/me', {
    method: 'PATCH',
    body: JSON.stringify({ name }),
  });
}

export async function changeMyPassword(currentPassword: string, newPassword: string) {
  return requestEnveloped('/api/v1/me/password', {
    method: 'POST',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}
```

`requestEnveloped`의 정확한 이름과 시그니처는 파일에서 확인해 기존 함수들과 같은 패턴을 따른다.

- 공지 조회 함수에 `groupId`와 `limit`을 붙이고, 응답의 `meta`를 함께 반환한다

- [ ] **Step 2: 막다른 길을 없앤다**

`app/groups/page.tsx:186-190`의 빈 상태를 팀 만들기 폼으로 바꾼다. 정확한 문구:

- 제목: `아직 속한 팀이 없습니다`
- 설명: `팀을 만들면 동료를 이메일로 초대할 수 있습니다.`
- 입력 placeholder: `팀 이름`
- 버튼: `팀 만들기`

제출하면 `createGroup(name)`을 호출하고, 성공 시 그룹 목록을 다시 불러와 새 그룹을 선택 상태로 만든다. 실패하면 기존 에러 표시 경로를 쓴다.

- [ ] **Step 3: 관리자 판정을 그룹 역할로 바꾼다**

`app/groups/page.tsx:20`의

```ts
const isAdmin = user?.role === 'admin';
```

를 **선택된 그룹에서의 내 역할**로 바꾼다.

```ts
const isAdmin = groups.find((g) => g.id === selectedGroupId)?.role === 'admin';
```

`groups`의 출처(컨텍스트인지 로컬 상태인지)는 파일을 읽고 맞춘다. 그룹을 바꾸면 `isAdmin`도 따라 바뀌어야 한다.

`:218`의 `m.role === 'admin'`은 그대로 둔다 — 이제 멤버십 역할이라 의미가 맞다.

- [ ] **Step 4: 빌드와 타입 검사**

Run: `cd onque-frontend && npm run build`
Expected: 성공. `user.role`을 지운 자리에서 타입 에러가 나면 그 호출부도 고친다.

- [ ] **Step 5: 커밋**

```bash
git add onque-frontend/lib/api.ts onque-frontend/app/groups/page.tsx
git commit -m "feat: 팀이 없을 때 팀 만들기 폼을 띄우고 관리자 판정을 그룹 역할로 전환"
```

---

### Task 8: 프론트엔드 — 프로필 페이지, 사이드바, 공지

**Files:**
- Create: `onque-frontend/app/profile/page.tsx`
- Modify: `onque-frontend/components/Sidebar.tsx`
- Modify: `onque-frontend/app/announcements/page.tsx`

**Interfaces:**
- Consumes: Task 6·7의 `getMe`, `createGroup`, `updateMyName`, `changeMyPassword`, 공지 API

- [ ] **Step 1: 프로필 페이지를 만든다**

`app/profile/page.tsx`. 기존 페이지(`app/groups/page.tsx`)의 레이아웃·카드·버튼 클래스를 그대로 따른다. 세 구역:

1. **내 정보** — 이름(입력), 이메일(읽기 전용 텍스트), 가입일. 버튼 `이름 저장`
2. **비밀번호 변경** — `현재 비밀번호`, `새 비밀번호` 입력 두 개. 버튼 `비밀번호 변경`. 성공 시 `비밀번호를 변경했습니다.`
3. **소속 팀** — 팀 이름과 역할 배지. 역할 표기는 `관리자` / `멤버`

이모지를 쓰지 않는다. 아이콘이 필요하면 사이드바가 쓰는 SVG 패턴을 따른다.

- [ ] **Step 2: 사이드바를 고친다**

- `components/Sidebar.tsx:168`의 `{user?.name} · {user?.role}`을 `{user?.name}`으로 바꾼다
- 네비게이션 항목에 `{ href: '/profile', label: '내 프로필' }`을 추가한다. 기존 항목들과 같은 SVG 아이콘 형식을 쓴다
- `/announcements` 항목의 label을 `전사 공지`에서 `팀 공지`로 바꾼다

- [ ] **Step 3: 공지 페이지를 고친다**

- `app/announcements/page.tsx:13`의 `const isAdmin = user?.role === 'admin';`을 선택된 그룹에서의 역할로 바꾼다 (Task 7과 같은 방식)
- 공지 조회에 현재 그룹의 `group_id`를 넘긴다
- 작성 요청 본문에 `group_id`를 포함한다
- 화면 제목이 "전사 공지"면 "팀 공지"로 바꾼다

- [ ] **Step 4: 빌드**

Run: `cd onque-frontend && npm run build`
Expected: 성공

Run: `cd onque-frontend && grep -rn "user?.role\|user\.role" app components lib`
Expected: 결과 없음

- [ ] **Step 5: 커밋**

```bash
git add onque-frontend/
git commit -m "feat: 프로필 탭 추가, 사이드바·공지 화면을 그룹 역할 기준으로 전환"
```

---

## 배포 절차

순서를 지킨다. 어기면 서비스 전체가 죽는다.

1. `venv/bin/pytest tests/ -q` — 전체 통과 확인
2. `cd onque-frontend && npm run build` — 성공 확인
3. **마이그레이션 먼저**: `PYTHONPATH=. venv/bin/python scripts/migrate_group_roles.py`
   - 기대 출력: `group_memberships.role 추가 + 그룹 생성자 1명을 admin으로`, `announcements.group_id 추가 (0행이라 백필 없음)`
4. 마이그레이션 검증:
   ```sql
   SELECT user_id, group_id, role FROM group_memberships;   -- (2, 3, 'admin')
   SELECT column_name, is_nullable FROM information_schema.columns
    WHERE table_name = 'announcements' AND column_name = 'group_id';
   ```
5. `git push origin main` — Render(백엔드)와 Vercel(프론트)이 각각 배포
6. 배포 확인:
   - `GET /openapi.json`에 `/api/v1/me/password`가 있는지
   - 인증 없이 `GET /api/v1/announcements?group_id=3` → 봉투 형식 401 (맨 500이 아님)
7. 육안 확인 (로그인 필요):
   - user 3(`nm2321@naver.com`)으로 로그인 → **팀 만들기 폼**이 보인다 (기존의 막다른 안내문이 아님)
   - user 2로 로그인 → 그룹 관리에 초대 폼이 보이고, 내 프로필 탭이 동작한다

## 검증 기준

전 과정이 이어져야 완료다.

1. 새 사용자가 가입한다 → 팀 만들기 화면이 보인다
2. 팀을 만든다 → 그 팀에서 admin이 된다
3. 미가입 이메일을 초대한다 → 대기 초대 목록에 뜬다
4. 그 이메일로 가입한다 → 자동 합류하고 role은 member다
5. 합류한 멤버가 초대를 시도한다 → 403 `GROUP_INVITE_FORBIDDEN`
6. 합류한 멤버가 공지 작성을 시도한다 → 403 `ANNOUNCEMENT_CREATE_FORBIDDEN`
7. 관리자가 공지를 쓴다 → 그 팀 멤버에게만 보인다
8. 두 번째 사용자가 자기 팀을 따로 만든다 → 첫 팀 데이터가 보이지 않는다

**8번이 이 변경의 존재 이유다.** 지금은 불가능하다.

## 범위 밖

| 항목 | 이유 |
|---|---|
| R-3 알림창 | B묶음 |
| R-5~R-8 회의록 | C묶음 |
| 프로필 사진 | 외부 저장소 연동 선행 필요 |
| `users.role` 컬럼 DROP | 신코드 안정화 후 별도 배포 |
| 관리자 위임 / 소유권 이전 | 마지막 관리자 제거만 막는다 (Task 3) |
