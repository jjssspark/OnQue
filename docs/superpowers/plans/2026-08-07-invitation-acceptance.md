# 초대 수락 절차 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 초대받은 사람이 **수락해야** 팀에 들어가게 만들어, 이메일 열거 오라클과 무동의 편입을 함께 닫는다.

**Architecture:** 받은 초대 API 3개를 먼저 **추가만** 하고(아무것도 깨지지 않음), 그다음 자동 합류를 제거하면서 기존 테스트를 수락 호출로 고친다. 순서를 반대로 하면 "초대는 됐는데 들어갈 방법이 없는" 구간이 생겨 태스크 중간에 테스트가 빨간불로 남는다 — A묶음이 겪은 TS-024를 반복하지 않기 위한 순서다. 데이터 모델은 바뀌지 않으므로 **마이그레이션이 없다.**

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (`Mapped[T]` + `mapped_column`), pytest, Next.js App Router, Neon Postgres (운영) / SQLite in-memory (테스트)

**스펙:** `docs/superpowers/specs/2026-08-07-invitation-acceptance-design.md`

## Global Constraints

- 모든 `/api/v1` 응답은 봉투 형식. `{"success": bool, "data": ..., "error": ...}`. `data`와 `error` 중 하나는 반드시 `null`.
- 에러는 `HTTPException(status, detail={"code": ..., "message": ...})`. **기존 에러 코드 문자열을 바꾸지 않는다** — 프론트가 `code`로 분기하므로 코드 변경은 깨는 변경이다. `GROUP_INVITE_ALREADY_MEMBER`, `GROUP_INVITE_ALREADY_SENT`, `GROUP_INVITE_FORBIDDEN`은 그대로 둔다.
- `main.py:43`에는 `HTTPException` 핸들러만 있다. 다른 예외가 새어나가면 봉투가 아닌 맨 500이 나간다. DB 제약 위반 가능 지점은 반드시 잡는다.
- **Alembic이 없다.** 이 플랜은 스키마를 바꾸지 않는다. `scripts/migrate_*.py`를 만들거나 고치지 않는다.
- 목록 엔드포인트는 페이지네이션 없이 전체를 반환하지 않는다. 기본 `limit=20`, 최대 100.
- 사용자 대면 문자열은 한국어. **이모지를 아이콘으로 쓰지 않는다.**
- 테스트는 `tests/conftest.py`의 `client` / `db_session` 픽스처를 쓴다. 두 픽스처는 같은 in-memory SQLite 엔진을 공유한다.
- SQLite는 `PRAGMA foreign_keys=ON` 없이는 FK를 강제하지 않는다. 이 프로젝트는 켜지 않는다. FK 캐스케이드에 의존하는 동작은 테스트로 검증할 수 없으므로 애플리케이션 코드에서 직접 처리한다.
- **각 태스크는 `venv/bin/pytest tests/ -q` 전체 통과 상태로 끝난다.** 허용 실패 집합을 두지 않는다.
- 이메일 비교는 항상 양쪽 `func.lower()`. 가입 컬럼이 대소문자를 구분해 저장한다.
- 여러 테스트 파일이 `_signup(client, email, name)` 헬퍼를 쓴다. 헬퍼가 없는 파일에는 **정의를 그대로 복사한다** — 테스트 파일끼리 import하지 않는다.
- 이메일은 파일 안에서 유일해야 한다. 같은 함수 안에서 같은 이메일로 두 번 가입하면 409다.
- 프론트 타입 검사는 `cd onque-frontend && npx tsc --noEmit`. 워크트리에서 `npm run build`는 Turbopack 심링크 문제로 실패하므로 `npx next build --webpack`을 쓴다 (TS-026).

---

### Task 1: 받은 초대 API 3개

**Files:**
- Modify: `routers/auth.py:10` — import 한 줄, 파일 끝에 엔드포인트 3개 추가
- Test: `tests/test_auth_routes.py`

**Interfaces:**
- Consumes: `routers.groups.join_group(db, user_id, group_id)` (이미 `routers/auth.py:11`에서 import됨), `models.GroupInvitation`
- Produces: `GET /api/v1/me/invitations`, `POST /api/v1/me/invitations/{invitation_id}/accept`, `DELETE /api/v1/me/invitations/{invitation_id}`. 새 에러 코드 `INVITATION_NOT_FOUND` (404)

이 태스크는 **순수 추가**다. 기존 동작을 하나도 바꾸지 않으므로 기존 테스트가 전부 그대로 통과해야 한다. 통과하지 않으면 의도치 않게 뭔가 건드린 것이다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_auth_routes.py` 끝에 추가한다. 이 파일에는 `_signup` 헬퍼가 이미 있으니 다시 정의하지 않는다 — 먼저 파일을 열어 확인하고, 없을 때만 Global Constraints의 정의를 복사한다.

```python
def _make_pending_invitation(db_session, group_id: int, email: str, invited_by: int) -> int:
    """대기 초대를 직접 만든다. 초대 엔드포인트는 Task 2 전까지 가입자를 즉시
    합류시키므로, 대기 상태를 만들려면 행을 직접 넣어야 한다."""
    from models import GroupInvitation

    inv = GroupInvitation(group_id=group_id, email=email, invited_by=invited_by)
    db_session.add(inv)
    db_session.commit()
    return inv.id


def test_my_invitations_lists_only_mine(client, db_session):
    owner = _signup(client, "inv-own@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    owner_id = client.get("/api/v1/me", headers=owner).json()["data"]["user"]["id"]

    guest = _signup(client, "inv-guest@t.dev", "손님")
    _signup(client, "inv-other@t.dev", "남")
    _make_pending_invitation(db_session, gid, "inv-guest@t.dev", owner_id)
    _make_pending_invitation(db_session, gid, "inv-other@t.dev", owner_id)

    rows = client.get("/api/v1/me/invitations", headers=guest).json()["data"]
    assert [r["group_id"] for r in rows] == [gid]
    assert rows[0]["group_name"] == "A팀"
    assert rows[0]["invited_by_name"] == "주인"


def test_invitation_is_not_membership_until_accepted(client, db_session):
    """이 변경의 존재 이유. 초대만으로 팀에 들어가면 안 된다."""
    owner = _signup(client, "inv2-own@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    owner_id = client.get("/api/v1/me", headers=owner).json()["data"]["user"]["id"]

    guest = _signup(client, "inv2-guest@t.dev", "손님")
    _make_pending_invitation(db_session, gid, "inv2-guest@t.dev", owner_id)

    assert client.get("/api/v1/me", headers=guest).json()["data"]["groups"] == []


def test_accepting_an_invitation_joins_as_member(client, db_session):
    owner = _signup(client, "inv3-own@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    owner_id = client.get("/api/v1/me", headers=owner).json()["data"]["user"]["id"]

    guest = _signup(client, "inv3-guest@t.dev", "손님")
    inv_id = _make_pending_invitation(db_session, gid, "inv3-guest@t.dev", owner_id)

    assert client.post(f"/api/v1/me/invitations/{inv_id}/accept", headers=guest).status_code == 200

    groups = client.get("/api/v1/me", headers=guest).json()["data"]["groups"]
    assert [(g["id"], g["role"]) for g in groups] == [(gid, "member")]
    assert client.get("/api/v1/me/invitations", headers=guest).json()["data"] == []


def test_declining_removes_the_invitation_without_joining(client, db_session):
    owner = _signup(client, "inv4-own@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    owner_id = client.get("/api/v1/me", headers=owner).json()["data"]["user"]["id"]

    guest = _signup(client, "inv4-guest@t.dev", "손님")
    inv_id = _make_pending_invitation(db_session, gid, "inv4-guest@t.dev", owner_id)

    assert client.delete(f"/api/v1/me/invitations/{inv_id}", headers=guest).status_code == 200
    assert client.get("/api/v1/me/invitations", headers=guest).json()["data"] == []
    assert client.get("/api/v1/me", headers=guest).json()["data"]["groups"] == []


def test_cannot_accept_someone_elses_invitation(client, db_session):
    """403으로 나누면 초대 id의 존재 여부가 새어나간다."""
    owner = _signup(client, "inv5-own@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    owner_id = client.get("/api/v1/me", headers=owner).json()["data"]["user"]["id"]

    _signup(client, "inv5-target@t.dev", "대상")
    attacker = _signup(client, "inv5-attacker@t.dev", "공격")
    inv_id = _make_pending_invitation(db_session, gid, "inv5-target@t.dev", owner_id)

    res = client.post(f"/api/v1/me/invitations/{inv_id}/accept", headers=attacker)
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "INVITATION_NOT_FOUND"
    assert client.delete(f"/api/v1/me/invitations/{inv_id}", headers=attacker).status_code == 404


def test_accepting_twice_is_not_found_the_second_time(client, db_session):
    owner = _signup(client, "inv6-own@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    owner_id = client.get("/api/v1/me", headers=owner).json()["data"]["user"]["id"]

    guest = _signup(client, "inv6-guest@t.dev", "손님")
    inv_id = _make_pending_invitation(db_session, gid, "inv6-guest@t.dev", owner_id)

    assert client.post(f"/api/v1/me/invitations/{inv_id}/accept", headers=guest).status_code == 200
    assert client.post(f"/api/v1/me/invitations/{inv_id}/accept", headers=guest).status_code == 404


def test_invitation_email_matching_ignores_case(client, db_session):
    """가입 컬럼은 대소문자를 구분해 저장한다. 초대 이메일도 마찬가지다."""
    owner = _signup(client, "inv7-own@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    owner_id = client.get("/api/v1/me", headers=owner).json()["data"]["user"]["id"]

    guest = _signup(client, "inv7-Guest@t.dev", "손님")
    _make_pending_invitation(db_session, gid, "inv7-guest@t.dev", owner_id)

    assert len(client.get("/api/v1/me/invitations", headers=guest).json()["data"]) == 1
```

- [ ] **Step 2: 실패를 확인한다**

Run: `venv/bin/pytest tests/test_auth_routes.py -q`
Expected: FAIL — `/api/v1/me/invitations`가 404 (라우트 없음)

- [ ] **Step 3: import를 추가한다**

`routers/auth.py:10`을 이렇게 바꾼다. `Group`만 새로 들어간다.

```python
from models import Group, GroupInvitation, User
```

- [ ] **Step 4: 엔드포인트 3개를 추가한다**

`routers/auth.py`의 `change_my_password` 아래(파일 끝)에 붙인다.

```python
def _pending_invitation_for(db: Session, user: User, invitation_id: int) -> GroupInvitation:
    """내 이메일로 온 대기 초대만 돌려준다.

    남의 초대나 이미 수락된 초대는 404다. 403으로 나누면 초대 id의 존재
    여부가 새어나간다 — permissions.py가 그룹에서 쓴 것과 같은 원칙이다.
    """
    inv = db.get(GroupInvitation, invitation_id)
    if (
        inv is None
        or inv.accepted_at is not None
        or inv.email.lower() != user.email.lower()
    ):
        raise HTTPException(
            status_code=404,
            detail={"code": "INVITATION_NOT_FOUND", "message": "초대를 찾을 수 없습니다."},
        )
    return inv


@router.get("/me/invitations")
def list_my_invitations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(
            GroupInvitation.id,
            GroupInvitation.group_id,
            Group.name,
            User.name,
            GroupInvitation.created_at,
        )
        .join(Group, Group.id == GroupInvitation.group_id)
        .join(User, User.id == GroupInvitation.invited_by)
        .where(
            func.lower(GroupInvitation.email) == current_user.email.lower(),
            GroupInvitation.accepted_at.is_(None),
        )
        .order_by(GroupInvitation.created_at.desc())
    ).all()

    return {
        "success": True,
        "data": [
            {
                "id": inv_id,
                "group_id": group_id,
                "group_name": group_name,
                "invited_by_name": inviter_name,
                "created_at": created_at.isoformat(),
            }
            for inv_id, group_id, group_name, inviter_name, created_at in rows
        ],
        "error": None,
    }


@router.post("/me/invitations/{invitation_id}/accept")
def accept_my_invitation(
    invitation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    inv = _pending_invitation_for(db, current_user, invitation_id)
    join_group(db, current_user.id, inv.group_id)
    inv.accepted_at = datetime.now(timezone.utc)
    db.commit()
    return {"success": True, "data": {"group_id": inv.group_id}, "error": None}


@router.delete("/me/invitations/{invitation_id}")
def decline_my_invitation(
    invitation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """거절은 행을 지운다. declined_at 컬럼을 두면 Alembic 없는 이 프로젝트에서
    마이그레이션 배포가 한 번 더 필요해지는데, 사내 규모에서 거절 이력의
    값이 그 비용보다 작다. 관리자가 다시 초대하면 새 행이 생긴다."""
    inv = _pending_invitation_for(db, current_user, invitation_id)
    db.delete(inv)
    db.commit()
    return {"success": True, "data": {"declined": True}, "error": None}
```

`join_group`은 `routers/groups.py:24`에 있고 `role="member"`로 멤버십과 기본 방 멤버십을 만든다. **먼저 그 함수를 열어 `db.commit()`을 스스로 하는지 확인하라.** 하지 않는다면 위 코드처럼 호출부에서 커밋한다. 이미 커밋한다면 중복 커밋을 뺀다.

- [ ] **Step 5: 테스트를 돌려 통과를 확인한다**

Run: `venv/bin/pytest tests/test_auth_routes.py -q`
Expected: PASS

Run: `venv/bin/pytest tests/ -q`
Expected: **전체 통과, 0 failed.** 이 태스크는 순수 추가라 기존 동작을 바꾸지 않는다. 깨지는 게 있으면 의도치 않게 뭔가 건드린 것이니 보고한다.

포그라운드로 실행하고 timeout 500000ms. 전체 스위트가 150~260초 걸린다.

- [ ] **Step 6: 커밋**

```bash
git add routers/auth.py tests/test_auth_routes.py
git commit -m "feat: 받은 초대 조회·수락·거절 엔드포인트 추가"
```

---

### Task 2: 자동 합류 제거와 초대 응답 단일화

**Files:**
- Modify: `routers/groups.py:201-261` — `invite_to_group_by_email`
- Modify: `routers/auth.py:59-70` — `signup`의 대기 초대 정산 블록 제거
- Test: `tests/test_group_routes.py`, `tests/test_group_invitations.py`, 그 밖에 자동 합류에 기대던 모든 테스트

**Interfaces:**
- Consumes: Task 1의 `POST /api/v1/me/invitations/{id}/accept`, `GET /api/v1/me/invitations`
- Produces: `POST /api/v1/groups/{group_id}/invitations`가 가입 여부와 무관하게 `{"status": "invited", "email": ...}`를 돌려준다. 응답에서 `user` 객체가 사라진다.

**이 태스크가 기존 테스트를 깨뜨린다.** 초대로 멤버를 만들던 테스트가 전부 수락 호출을 넣도록 고쳐져야 한다. Task 1이 수락 엔드포인트를 이미 만들어 뒀으므로 이 태스크는 0 failed로 끝날 수 있다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_group_routes.py`에 추가한다. `_signup` 헬퍼가 이 파일에 이미 있다.

```python
def test_invite_response_is_identical_for_registered_and_unregistered(client):
    """이 변경의 존재 이유. 응답이 다르면 임의 이메일의 가입 여부를 알아낼 수 있다."""
    owner = _signup(client, "enum-own@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    _signup(client, "enum-registered@t.dev", "가입자")

    registered = client.post(
        f"/api/v1/groups/{gid}/invitations",
        json={"email": "enum-registered@t.dev"},
        headers=owner,
    )
    unregistered = client.post(
        f"/api/v1/groups/{gid}/invitations",
        json={"email": "enum-stranger@t.dev"},
        headers=owner,
    )

    assert registered.status_code == unregistered.status_code == 200
    assert registered.json()["data"] == {"status": "invited", "email": "enum-registered@t.dev"}
    assert unregistered.json()["data"] == {"status": "invited", "email": "enum-stranger@t.dev"}
    # 이메일 값 외에는 키 구성이 완전히 같아야 한다
    assert set(registered.json()["data"]) == set(unregistered.json()["data"])


def test_inviting_a_registered_user_does_not_join_them(client):
    owner = _signup(client, "noauto-own@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    guest = _signup(client, "noauto-guest@t.dev", "손님")

    client.post(
        f"/api/v1/groups/{gid}/invitations",
        json={"email": "noauto-guest@t.dev"},
        headers=owner,
    )

    assert client.get("/api/v1/me", headers=guest).json()["data"]["groups"] == []
    rows = client.get("/api/v1/me/invitations", headers=guest).json()["data"]
    assert [r["group_id"] for r in rows] == [gid]


def test_signing_up_with_an_invited_email_does_not_auto_join(client):
    """가입 자체를 동의로 보지 않는다. 규칙은 하나 — 누구든 수락해야 들어간다."""
    owner = _signup(client, "nosignup-own@t.dev", "주인")
    gid = client.post("/api/v1/groups", json={"name": "A팀"}, headers=owner).json()["data"]["id"]
    client.post(
        f"/api/v1/groups/{gid}/invitations",
        json={"email": "nosignup-new@t.dev"},
        headers=owner,
    )

    newcomer = _signup(client, "nosignup-new@t.dev", "신규")

    assert client.get("/api/v1/me", headers=newcomer).json()["data"]["groups"] == []
    rows = client.get("/api/v1/me/invitations", headers=newcomer).json()["data"]
    assert [r["group_id"] for r in rows] == [gid]
```

- [ ] **Step 2: 실패를 확인한다**

Run: `venv/bin/pytest tests/test_group_routes.py -q`
Expected: FAIL — 가입자 초대가 `{"status": "joined", "user": {...}}`를 돌려주고, 가입 시 자동 합류한다

- [ ] **Step 3: 초대 생성에서 가입자 분기를 제거한다**

`routers/groups.py`의 `invite_to_group_by_email` 본문을 이렇게 바꾼다. `require_group_admin` 호출과 `email` 정규화는 그대로 둔다.

```python
    email = body.email.strip().lower()

    # 이미 우리 팀 멤버인지 확인한다. 관리자가 GET /groups/{id}/members로
    # 이미 볼 수 있는 정보라 이 409는 새로 새는 것이 없다.
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user and db.get(GroupMembership, {"user_id": user.id, "group_id": group_id}):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "GROUP_INVITE_ALREADY_MEMBER",
                "message": "이미 이 그룹에 있는 사람입니다.",
            },
        )

    existing = db.scalar(
        select(GroupInvitation).where(
            GroupInvitation.group_id == group_id, GroupInvitation.email == email
        )
    )
    if existing and existing.accepted_at is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "GROUP_INVITE_ALREADY_SENT",
                "message": "이미 초대해 둔 이메일입니다.",
            },
        )

    # 가입자든 미가입자든 여기 하나로 모인다. 응답이 갈리면 임의 이메일의
    # 가입 여부를 알아낼 수 있다.
    _upsert_invitation(db, group_id, email, current_user.id, accepted=False)
    db.commit()
    return {
        "success": True,
        "data": {"status": "invited", "email": email},
        "error": None,
    }
```

`_serialize_invitation`은 같은 파일의 `list_group_invitations`가 계속 쓰므로 지우지 않는다. `join_group`은 이 파일에 **정의된** 함수이고 `routers/auth.py`가 import하므로 정의를 반드시 유지한다 — 이 파일 안의 호출부만 사라진다.

- [ ] **Step 4: 가입 시 자동 합류를 제거한다**

`routers/auth.py:59-70`의 블록을 통째로 지운다. 지울 대상은 이것이다.

```python
    # 가입 전에 받아둔 초대를 여기서 정산한다. 이 단계가 없으면 초대가 영영 닿지 않는다.
    pending = db.scalars(
        select(GroupInvitation).where(
            func.lower(GroupInvitation.email) == body.email.lower(),
            GroupInvitation.accepted_at.is_(None),
        )
    ).all()
    for invitation in pending:
        join_group(db, user.id, invitation.group_id)
        invitation.accepted_at = datetime.now(timezone.utc)
    if pending:
        db.commit()
```

`join_group`·`GroupInvitation`·`Group`·`func`·`datetime`·`timezone` import는 **지우지 마라.** Task 1이 추가한 `/me/invitations` 엔드포인트들이 전부 쓴다.

- [ ] **Step 5: 깨진 기존 테스트를 고친다**

Run: `venv/bin/pytest tests/ -q`

초대로 멤버를 만들던 테스트가 깨진다. 최소한 이것들이다 — **실제 목록은 실행해서 확인한다.**

- `tests/test_group_routes.py::test_invited_member_joins_as_member_not_admin`
- `tests/test_group_routes.py::test_member_list_returns_membership_role_not_user_role`
- `tests/test_group_routes.py::test_member_cannot_invite`
- `tests/test_group_routes.py::test_member_can_see_pending_invitations`
- `tests/test_group_invitations.py`에서 초대 후 합류를 단언하는 것들
- `tests/test_announcement_routes.py::test_member_cannot_write_announcement`
- `tests/test_group_scoping.py`·`tests/test_chat_rooms.py`에서 초대로 멤버를 만드는 것들

고치는 방법은 하나다. **초대 직후 그 사람이 수락하도록 두 줄을 넣는다.**

```python
    client.post(f"/api/v1/groups/{gid}/invitations", json={"email": "mem@t.dev"}, headers=owner)
    member = _signup(client, "mem@t.dev", "멤버")
    # 초대만으로는 합류하지 않는다. 수락해야 멤버가 된다.
    inv_id = client.get("/api/v1/me/invitations", headers=member).json()["data"][0]["id"]
    client.post(f"/api/v1/me/invitations/{inv_id}/accept", headers=member)
```

같은 패턴이 여러 파일에 반복되지만 **테스트 파일끼리 import하지 않는다** — 필요한 파일마다 위 네 줄을 복사한다.

`test_invited_member_joins_as_member_not_admin`은 이름이 더 이상 정확하지 않다. `test_accepted_invitation_makes_a_member_not_admin`으로 바꾸고 본문에 수락을 넣는다. **이름과 본문이 어긋난 테스트를 남기지 않는다** — TS-025가 정확히 그 문제였다.

`GROUP_INVITE_ALREADY_SENT`·`GROUP_INVITE_ALREADY_MEMBER`를 단언하던 테스트는 그대로 통과해야 한다. 깨진다면 의도하지 않은 변경이 있는 것이니 코드를 고친다.

**단언을 느슨하게 만들지 마라.** "멤버가 됐다"를 "요청이 200이다"로 바꾸는 식의 수정은 결함이다.

- [ ] **Step 6: 전체를 돌려 0 failed를 확인한다**

Run: `venv/bin/pytest tests/ -q`
Expected: **0 failed.** 포그라운드, timeout 500000ms.

실패가 남으면 허용하지 말고 원인을 찾는다. 이 플랜에는 실패 허용 집합이 없다.

- [ ] **Step 7: 커밋**

```bash
git add routers/groups.py routers/auth.py tests/
git commit -m "feat: 초대 응답을 가입 여부와 무관하게 단일화하고 자동 합류를 제거"
```

---

### Task 3: 프론트엔드 — 받은 초대 노출

**Files:**
- Modify: `onque-frontend/lib/api.ts` — 함수 3개 추가, `inviteToGroupByEmail` 반환 타입 수정
- Create: `onque-frontend/components/ReceivedInvitations.tsx`
- Modify: `onque-frontend/app/groups/page.tsx` — 최상단 마운트, `status === 'joined'` 분기 제거
- Modify: `onque-frontend/app/profile/page.tsx` — "소속 팀" 구역 위에 마운트

**Interfaces:**
- Consumes: Task 1·2의 `GET /api/v1/me/invitations`, `POST /api/v1/me/invitations/{id}/accept`, `DELETE /api/v1/me/invitations/{id}`, 그리고 새 초대 생성 응답 `{status: 'invited', email: string}`
- Produces: `<ReceivedInvitations onChanged={...} />` — 수락·거절 후 부모가 그룹 목록을 다시 불러오게 하는 콜백

- [ ] **Step 1: `lib/api.ts`를 고친다**

먼저 파일을 열어 봉투 헬퍼의 **실제 이름과 시그니처**를 확인한다(`requestEnveloped` / `requestEnvelopedWithMeta`). 이름이 다르면 실제 이름을 쓰고, 새 함수도 기존 함수들과 같은 패턴을 따른다.

```ts
export type ReceivedInvitation = {
  id: number;
  group_id: number;
  group_name: string;
  invited_by_name: string;
  created_at: string;
};

export async function listMyInvitations() {
  return requestEnveloped<ReceivedInvitation[]>('/api/v1/me/invitations');
}

export async function acceptInvitation(invitationId: number) {
  return requestEnveloped<{ group_id: number }>(
    `/api/v1/me/invitations/${invitationId}/accept`,
    { method: 'POST' },
  );
}

export async function declineInvitation(invitationId: number) {
  return requestEnveloped<{ declined: boolean }>(
    `/api/v1/me/invitations/${invitationId}`,
    { method: 'DELETE' },
  );
}
```

`inviteToGroupByEmail`의 반환 타입을 `{ status: 'invited'; email: string }`으로 바꾼다. 기존 타입에 `'joined' | 'pending'` 유니온이나 `user` 필드가 있으면 지운다.

- [ ] **Step 2: `ReceivedInvitations` 컴포넌트를 만든다**

`onque-frontend/components/ReceivedInvitations.tsx`.

```tsx
'use client';

import { useCallback, useEffect, useState } from 'react';

import {
  acceptInvitation,
  declineInvitation,
  listMyInvitations,
  type ReceivedInvitation,
} from '@/lib/api';

type Props = {
  onChanged: () => void | Promise<void>;
};

export function ReceivedInvitations({ onChanged }: Props) {
  const [invitations, setInvitations] = useState<ReceivedInvitation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      setInvitations(await listMyInvitations());
    } catch (err) {
      setError(err instanceof Error ? err.message : '초대를 불러오지 못했습니다.');
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function respond(id: number, accept: boolean) {
    setBusyId(id);
    setError(null);
    try {
      if (accept) {
        await acceptInvitation(id);
      } else {
        await declineInvitation(id);
      }
      setInvitations((prev) => prev.filter((i) => i.id !== id));
      await onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : '처리하지 못했습니다.');
      await load();
    } finally {
      setBusyId(null);
    }
  }

  if (invitations.length === 0 && !error) return null;

  return (
    <section>
      <h2>받은 초대</h2>
      {error && <p role="alert">{error}</p>}
      <ul>
        {invitations.map((inv) => (
          <li key={inv.id}>
            <div>
              <p>{inv.group_name}</p>
              <p>{inv.invited_by_name}님이 초대했습니다.</p>
            </div>
            <div>
              <button type="button" disabled={busyId === inv.id} onClick={() => respond(inv.id, true)}>
                수락
              </button>
              <button type="button" disabled={busyId === inv.id} onClick={() => respond(inv.id, false)}>
                거절
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
```

**클래스는 위 골격에 채워 넣는다.** `app/groups/page.tsx`의 카드·제목·버튼 클래스를 그대로 복사해 쓰고 새 디자인 언어를 만들지 않는다. **이모지를 쓰지 않는다.**

`if (invitations.length === 0 && !error) return null;`이 중요하다 — 초대가 없으면 빈 카드가 아니라 아무것도 그리지 않는다. 이게 있어야 기존 화면이 그대로 유지된다.

- [ ] **Step 3: 그룹 페이지에 붙인다**

`app/groups/page.tsx`:

1. 반환 JSX의 **첫 자식**으로 `<ReceivedInvitations onChanged={refreshMe} />`를 둔다. `refreshMe`의 실제 이름은 `components/AuthContext.tsx`에서 확인한다 — 그룹 목록을 다시 불러오는 함수여야 수락 직후 새 팀이 화면에 나타난다.
2. `result.status === 'joined'` 분기를 제거한다. 초대 성공 안내를 하나로 만든다: `초대했습니다. 상대가 수락하면 팀에 합류합니다.`
3. 빈 상태 우선순위 — `groups.length === 0`일 때 팀 만들기 폼이 뜨는데, **받은 초대 카드가 그보다 위에** 있어야 한다. 1번대로 첫 자식에 두면 자동으로 만족된다. 초대가 0건이면 컴포넌트가 `null`을 돌려주므로 지금과 같은 화면이 된다.

- [ ] **Step 4: 프로필 페이지에 붙인다**

`app/profile/page.tsx`의 "소속 팀" 구역 **바로 위**에 `<ReceivedInvitations onChanged={refreshMe} />`를 둔다. 같은 컴포넌트를 그대로 재사용한다.

- [ ] **Step 5: 타입 검사와 빌드**

Run: `cd onque-frontend && npx tsc --noEmit`
Expected: 에러 0건. 포그라운드, timeout 300000ms.

Run: `cd onque-frontend && npx next build --webpack`
Expected: 성공. 포그라운드, timeout 600000ms.

`npm run build`(Turbopack)는 이 워크트리에서 `node_modules` 심링크 때문에 실패한다(TS-026). **`next.config.ts`를 고치지 마라.**

- [ ] **Step 6: 커밋**

```bash
git add onque-frontend/lib/api.ts onque-frontend/components/ReceivedInvitations.tsx onque-frontend/app/groups/page.tsx onque-frontend/app/profile/page.tsx
git commit -m "feat: 받은 초대를 그룹·프로필 화면에 노출하고 수락·거절 연결"
```

---

## 배포 절차

**마이그레이션이 없다.** 스키마가 바뀌지 않으므로 A묶음의 "마이그레이션 먼저" 제약이 이 배포에는 적용되지 않는다.

1. `venv/bin/pytest tests/ -q` — 0 failed 확인
2. `cd onque-frontend && npx next build --webpack` — 성공 확인
3. `git push origin main` — Render(백엔드)와 Vercel(프론트)이 각각 배포

**배포 순서 주의.** 백엔드와 프론트가 따로 배포되므로 사이에 틈이 생긴다.

- 백엔드가 먼저 뜨면: 구프론트가 초대 응답의 `status === 'joined'`를 기다리는데 안 오므로 안내 문구만 어긋난다. 초대 자체는 정상 생성된다.
- 프론트가 먼저 뜨면: `/api/v1/me/invitations`가 404라 받은 초대 카드가 에러를 표시한다.

**백엔드를 먼저 배포하는 쪽이 안전하다.**

4. 배포 확인:
   - `GET /openapi.json`에 `/api/v1/me/invitations`가 있는지
   - 인증 없이 `GET /api/v1/me/invitations` → 봉투 형식 401 (맨 500이 아님)

## 검증 기준

전 과정이 이어져야 완료다.

1. 관리자가 **가입자** 이메일을 초대한다 → 응답이 `{"status": "invited", "email": ...}`
2. 관리자가 **미가입자** 이메일을 초대한다 → **1번과 동일한 구조의 응답**
3. 초대받은 가입자의 `/api/v1/me` 그룹 목록에 그 팀이 아직 없다
4. 그 사용자의 그룹 페이지 최상단에 받은 초대 카드가 뜬다
5. 수락한다 → 그 팀에 `member`로 합류하고 카드가 사라진다
6. 다른 초대를 거절한다 → 카드가 사라지고 멤버가 아니다
7. 남의 초대 id로 수락을 시도한다 → 404 `INVITATION_NOT_FOUND`
8. 초대받은 이메일로 새로 가입한다 → 자동 합류하지 않고 초대 카드가 보인다

**2번이 이 변경의 존재 이유다.** 두 응답이 다르면 임의 이메일의 가입 여부를 알아낼 수 있다.

A묶음 검증 기준 4번이 이 플랜으로 개정된다 — "가입하면 자동 합류"에서 "가입하면 대기 초대가 보이고, 수락하면 합류"로.

## 범위 밖

| 항목 | 이유 |
|---|---|
| 초대 레이트 리밋 | 공개 서비스 전환 시 필요. 사내 단계에선 과잉 |
| 초대 알림 메일 | 외부 메일 발송 연동 선행 필요 |
| 거절 이력 보관 (`declined_at`) | 마이그레이션 비용 대비 값이 작다 |
| 가입 플로우를 초대 기반으로 닫기 | 가입 모델이 미확정 |
| 사이드바 초대 배지 | 전역 상태나 폴링이 필요. 대시보드 건과 함께 검토 |
