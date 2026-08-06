# 자율 약속 추적 (Commitment Tracking) 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 클라이언트에게 한 약속을 통화·문서·채팅에서 자동 추출해 제안 상태로 쌓고, 사람이 일괄 확인하면 기한을 추적한다.

**Architecture:** 신규 테이블 `clients`/`commitments`를 추가하고, 기존 Gemini 요약 응답 스키마에 `commitments[]` 필드만 얹어 추가 API 호출 없이 추출한다. 채팅은 방 단위 배치로 훑고, Render 무료 티어에 상주 워커가 없으므로 `GET /api/v1/commitments` 요청에 스윕을 편승시킨다. 기한 경고는 저장하지 않고 조회 시 계산한다.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (`Mapped`/`mapped_column`), Pydantic v2, pytest + TestClient (SQLite in-memory), google-genai (`gemini-2.5-flash`), Next.js App Router + Tailwind

**설계 문서:** `docs/superpowers/specs/2026-08-06-autonomous-commitment-tracking-design.md`

## Global Constraints

- 신규 엔드포인트는 전부 `APIRouter(prefix="/api/v1")`에 두고 **envelope 형식**을 지킨다: `{"success": true, "data": ..., "error": null}`. `main.py`에 직접 붙은 구 엔드포인트(`/todos` 등)는 envelope가 없지만 **그 패턴을 따라가지 않는다.**
- 에러는 `HTTPException(status_code, detail={"code": ..., "message": ...})` 형태로 던진다. `main.py:37`의 핸들러가 envelope로 감싼다.
- 목록 엔드포인트는 기본 `limit=20`, 최대 100.
- 날짜: `due_date`는 `YYYY-MM-DD` 문자열, 타임스탬프는 ISO 8601 UTC (`.isoformat()`).
- **UI에 이모지를 아이콘으로 쓰지 않는다.**
- Gemini 모델은 `gemini_service.MODEL` 상수를 쓴다. 하드코딩 금지.
- SQLAlchemy는 2.0 스타일(`Mapped[T]` + `mapped_column`). `models.py` 기존 클래스와 동일하게.
- 문자열 enum은 모듈 상수 튜플 + `CheckConstraint` f-string. `models.py:138-145`의 `Document` 패턴과 동일하게.
- 접근 제어는 항상 `group_id` 기준. `client_id`로 권한을 판정하지 않는다.
- 테스트는 `pytest`. `tests/conftest.py`가 주는 `client`(TestClient)와 `db_session`(직접 시딩용) 픽스처를 쓴다.
- **Alembic이 없다.** `Base.metadata.create_all`은 신규 테이블만 만든다. 기존 테이블 컬럼 추가는 `scripts/` 마이그레이션 스크립트로 별도 처리한다.
- 커밋 메시지는 한국어 허용. `<type>: <설명>` 형식.

---

### Task 1: 데이터 모델과 마이그레이션

**Files:**
- Modify: `models.py` (파일 끝에 추가, `ChatRoom`·`Group` 클래스 수정)
- Create: `scripts/migrate_add_commitments.py`
- Test: `tests/test_commitment_models.py`

**Interfaces:**
- Consumes: 없음 (첫 작업)
- Produces:
  - `models.Client` — `id: int`, `group_id: int`, `name: str`, `created_at: datetime`
  - `models.Commitment` — `id: int`, `group_id: int`, `client_id: int | None`, `content: str`, `due_date: date | None`, `status: str`, `source_type: str`, `source_id: int | None`, `evidence: str`, `created_at: datetime`, `updated_at: datetime`, `confirmed_at: datetime | None`
  - `models.COMMITMENT_STATUSES: tuple[str, ...]` = `("proposed", "confirmed", "fulfilled", "dismissed")`
  - `models.COMMITMENT_SOURCE_TYPES: tuple[str, ...]` = `("call", "document", "chat")`
  - `models.ChatRoom.last_scanned_message_id: int | None`
  - `models.Group.last_swept_at: datetime | None`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_commitment_models.py`:

```python
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from models import Client, Commitment


def test_client_name_unique_per_group(client, db_session):
    db_session.add(Client(group_id=1, name="A사"))
    db_session.commit()

    db_session.add(Client(group_id=1, name="A사"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_same_client_name_allowed_in_other_group(client, db_session):
    db_session.add(Client(group_id=1, name="A사"))
    db_session.add(Client(group_id=2, name="A사"))
    db_session.commit()

    assert db_session.query(Client).count() == 2


def test_commitment_defaults_to_proposed(client, db_session):
    c = Commitment(
        group_id=1,
        content="시안 3종 전달",
        source_type="call",
        evidence="다음 주 수요일까지 시안 세 개 보내드릴게요",
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)

    assert c.status == "proposed"
    assert c.client_id is None
    assert c.due_date is None
    assert c.confirmed_at is None


def test_commitment_rejects_unknown_status(client, db_session):
    db_session.add(
        Commitment(
            group_id=1,
            content="시안 전달",
            source_type="call",
            evidence="보내드릴게요",
            status="unknown",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_commitment_accepts_due_date_and_client(client, db_session):
    a = Client(group_id=1, name="A사")
    db_session.add(a)
    db_session.commit()

    c = Commitment(
        group_id=1,
        client_id=a.id,
        content="시안 3종 전달",
        due_date=date(2026, 8, 13),
        source_type="chat",
        source_id=42,
        evidence="수요일까지 드릴게요",
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)

    assert c.client_id == a.id
    assert c.due_date == date(2026, 8, 13)
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `pytest tests/test_commitment_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'Client' from 'models'`

- [ ] **Step 3: 모델을 추가한다**

`models.py` 상단 상수 구역(`DOCUMENT_CATEGORIES` 근처)에 추가:

```python
COMMITMENT_STATUSES = ("proposed", "confirmed", "fulfilled", "dismissed")
COMMITMENT_SOURCE_TYPES = ("call", "document", "chat")
```

`models.py` 끝에 추가:

```python
class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (
        UniqueConstraint("group_id", "name", name="uq_clients_group_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Commitment(Base):
    """클라이언트에게 한 약속. 내부 작업인 Todo와 구분된다 —
    상대(client_id)와 근거(evidence)를 갖고, 놓치면 신뢰와 돈이 걸린다."""

    __tablename__ = "commitments"
    __table_args__ = (
        CheckConstraint(
            f"status IN {COMMITMENT_STATUSES}", name="ck_commitments_status"
        ),
        CheckConstraint(
            f"source_type IN {COMMITMENT_SOURCE_TYPES}",
            name="ck_commitments_source_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), nullable=False)
    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.id"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="proposed")
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    # documents.id 또는 chat_messages.id. 원본이 지워져도 약속은 남아야 하므로 FK를 걸지 않는다.
    source_id: Mapped[int | None] = mapped_column(nullable=True)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

`models.py` import 줄에 `UniqueConstraint`를 추가한다 (`CheckConstraint`가 이미 import되어 있는 그 줄).

기존 `ChatRoom` 클래스에 컬럼 추가:

```python
    # 방 단위 배치 스캔의 진행 지점. null이면 아직 훑은 적 없음 — 백필 불필요.
    last_scanned_message_id: Mapped[int | None] = mapped_column(nullable=True)
```

기존 `Group` 클래스에 컬럼 추가:

```python
    # 요청 편승 스윕의 쿨다운 기준. null이면 한 번도 안 돌았음 — 백필 불필요.
    last_swept_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `pytest tests/test_commitment_models.py -v`
Expected: 5 passed

기존 테스트가 깨지지 않았는지도 확인한다.
Run: `pytest -q`
Expected: 전부 통과

- [ ] **Step 5: 마이그레이션 스크립트를 쓴다**

`create_all`은 신규 테이블만 만든다. 배포된 Postgres의 `chat_rooms`/`groups`에는 컬럼이 안 생기므로 별도 스크립트가 필요하다.

`scripts/migrate_add_commitments.py`:

```python
"""자율 약속 추적 마이그레이션.

실행 순서:
1. 서버를 한 번 기동해 clients/commitments 테이블을 만든다
   (main.py의 Base.metadata.create_all이 신규 테이블만 생성한다).
2. 이 스크립트를 실행한다 — 기존 chat_rooms/groups 테이블에 컬럼을 추가한다.

두 컬럼 모두 nullable이고 null이 "아직 없음"을 뜻하므로 백필하지 않는다.
last_scanned_message_id가 null이면 방 전체가 미스캔 상태로 취급되고,
last_swept_at이 null이면 다음 조회에서 스윕이 한 번 돈다. 둘 다 의도된 동작이다.
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
        if not _column_exists(conn, "chat_rooms", "last_scanned_message_id"):
            conn.execute(
                text("ALTER TABLE chat_rooms ADD COLUMN last_scanned_message_id INTEGER")
            )
            print("chat_rooms.last_scanned_message_id 추가")
        else:
            print("chat_rooms.last_scanned_message_id 이미 있음")

        if not _column_exists(conn, "groups", "last_swept_at"):
            conn.execute(
                text("ALTER TABLE groups ADD COLUMN last_swept_at TIMESTAMPTZ")
            )
            print("groups.last_swept_at 추가")
        else:
            print("groups.last_swept_at 이미 있음")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: 커밋**

```bash
git add models.py scripts/migrate_add_commitments.py tests/test_commitment_models.py
git commit -m "feat: Client/Commitment 모델과 마이그레이션 스크립트"
```

---

### Task 2: 클라이언트 CRUD API

**Files:**
- Create: `routers/commitments.py`
- Modify: `main.py:54-57` (라우터 등록 구역)
- Test: `tests/test_client_routes.py`

**Interfaces:**
- Consumes: `models.Client` (Task 1)
- Produces:
  - `routers.commitments.router` — `APIRouter(prefix="/api/v1", tags=["commitments"])`
  - `GET /api/v1/clients?group_id=` → `{"success": true, "data": [{id, name, created_at}], "error": null}`
  - `POST /api/v1/clients` body `{group_id, name}` → 동일 형태의 단건
  - `routers.commitments._serialize_client(c: Client) -> dict`
  - `routers.commitments._require_group_member(user: User, group_id: int, db: Session) -> None`
  - `routers.commitments._ok(data) -> dict`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_client_routes.py`:

```python
def _setup(client):
    token = client.post(
        "/api/v1/auth/signup",
        json={"email": "admin@onque.dev", "password": "password123", "name": "관리자"},
    ).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    group_a = client.post("/api/v1/groups", json={"name": "A팀"}, headers=headers).json()["data"]
    group_b = client.post("/api/v1/groups", json={"name": "B팀"}, headers=headers).json()["data"]
    return headers, group_a["id"], group_b["id"]


def test_create_and_list_client(client):
    headers, group_a, _ = _setup(client)

    created = client.post(
        "/api/v1/clients", json={"group_id": group_a, "name": "A사"}, headers=headers
    )
    assert created.status_code == 200
    assert created.json()["success"] is True
    assert created.json()["data"]["name"] == "A사"

    listed = client.get("/api/v1/clients", params={"group_id": group_a}, headers=headers)
    assert [c["name"] for c in listed.json()["data"]] == ["A사"]


def test_duplicate_client_name_rejected(client):
    headers, group_a, _ = _setup(client)
    client.post("/api/v1/clients", json={"group_id": group_a, "name": "A사"}, headers=headers)

    dup = client.post(
        "/api/v1/clients", json={"group_id": group_a, "name": "A사"}, headers=headers
    )
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "CLIENT_NAME_DUPLICATE"


def test_clients_isolated_between_groups(client):
    headers, group_a, group_b = _setup(client)
    client.post("/api/v1/clients", json={"group_id": group_a, "name": "A사"}, headers=headers)

    res = client.get("/api/v1/clients", params={"group_id": group_b}, headers=headers)
    assert res.json()["data"] == []


def test_client_requires_group_membership(client):
    headers, group_a, _ = _setup(client)
    other = client.post(
        "/api/v1/auth/signup",
        json={"email": "other@onque.dev", "password": "password123", "name": "외부인"},
    ).json()["data"]["token"]

    res = client.get(
        "/api/v1/clients",
        params={"group_id": group_a},
        headers={"Authorization": f"Bearer {other}"},
    )
    assert res.status_code == 403
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `pytest tests/test_client_routes.py -v`
Expected: FAIL — 404 (라우트 없음)

- [ ] **Step 3: 라우터를 만든다**

`routers/commitments.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import get_current_user
from db import get_db
from models import Client, GroupMembership, User

router = APIRouter(prefix="/api/v1", tags=["commitments"])


def _require_group_member(user: User, group_id: int, db: Session) -> None:
    """main.py의 동명 함수와 같은 규칙. 라우터가 main을 import하면 순환이 되므로
    여기 둔다."""
    member = db.execute(
        select(GroupMembership).where(
            GroupMembership.user_id == user.id,
            GroupMembership.group_id == group_id,
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "COMMITMENT_ACCESS_FORBIDDEN",
                "message": "이 그룹에 접근할 수 없습니다",
            },
        )


def _ok(data):
    return {"success": True, "data": data, "error": None}


def _serialize_client(c: Client) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "created_at": c.created_at.isoformat(),
    }


class ClientCreateBody(BaseModel):
    group_id: int
    name: str


@router.get("/clients")
def list_clients(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_group_member(current_user, group_id, db)
    rows = db.execute(
        select(Client).where(Client.group_id == group_id).order_by(Client.name)
    ).scalars().all()
    return _ok([_serialize_client(c) for c in rows])


@router.post("/clients")
def create_client(
    body: ClientCreateBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_group_member(current_user, body.group_id, db)
    name = body.name.strip()
    if not name:
        raise HTTPException(
            status_code=400,
            detail={"code": "CLIENT_NAME_INVALID", "message": "클라이언트 이름이 비어 있습니다"},
        )

    existing = db.execute(
        select(Client).where(Client.group_id == body.group_id, Client.name == name)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={"code": "CLIENT_NAME_DUPLICATE", "message": "이미 등록된 클라이언트입니다"},
        )

    created = Client(group_id=body.group_id, name=name)
    db.add(created)
    db.commit()
    db.refresh(created)
    return _ok(_serialize_client(created))
```

`main.py` 상단의 다른 `from routers... import` 옆에 추가:

```python
from routers.commitments import router as commitments_router
```

`app.include_router(users_router)` 다음 줄에 추가:

```python
app.include_router(commitments_router)
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `pytest tests/test_client_routes.py -v`
Expected: 4 passed

- [ ] **Step 5: 커밋**

```bash
git add routers/commitments.py main.py tests/test_client_routes.py
git commit -m "feat: 클라이언트 등록/조회 API"
```

---

### Task 3: 요약 파이프라인에서 약속 추출

**Files:**
- Modify: `gemini_service.py` (`_SUMMARY_SCHEMA`, `normalize_summary`, 프롬프트 2개)
- Create: `commitment_service.py`
- Modify: `main.py:115-152` (`_summarize_and_store`)
- Test: `tests/test_commitment_extraction.py`

**Interfaces:**
- Consumes: `models.Client`, `models.Commitment` (Task 1)
- Produces:
  - `gemini_service._COMMITMENT_ITEM_SCHEMA: dict` — 다른 스키마에서 재사용하는 약속 항목 스키마
  - `gemini_service.normalize_summary(raw)` 반환값에 `"commitments": list[dict]` 추가. 각 항목은 `{"content": str, "client_name": str, "due_date": str, "evidence": str}`
  - `commitment_service.resolve_client_id(db: Session, group_id: int, client_name: str) -> int | None`
  - `commitment_service.create_commitments(db: Session, group_id: int, items: list[dict], source_type: str, source_id: int | None) -> list[Commitment]`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_commitment_extraction.py`:

```python
from datetime import date

import commitment_service
from gemini_service import normalize_summary
from models import Client, Commitment


def test_normalize_summary_extracts_commitments():
    raw = {
        "headline": "A사 킥오프",
        "key_points": [],
        "requests": [],
        "action_items": [],
        "notes": "",
        "commitments": [
            {
                "content": "시안 3종 전달",
                "client_name": "A사",
                "due_date": "2026-08-13",
                "evidence": "수요일까지 시안 세 개 보내드릴게요",
            }
        ],
    }
    result = normalize_summary(raw)
    assert result["commitments"] == [
        {
            "content": "시안 3종 전달",
            "client_name": "A사",
            "due_date": "2026-08-13",
            "evidence": "수요일까지 시안 세 개 보내드릴게요",
        }
    ]


def test_normalize_summary_defaults_commitments_to_empty():
    raw = {"headline": "회의", "key_points": [], "requests": [], "action_items": [], "notes": ""}
    assert normalize_summary(raw)["commitments"] == []


def test_normalize_summary_drops_commitment_without_evidence():
    """근거 없는 약속은 사람이 판단할 수 없으므로 버린다."""
    raw = {
        "headline": "",
        "key_points": [],
        "requests": [],
        "action_items": [],
        "notes": "",
        "commitments": [
            {"content": "뭔가 하기", "client_name": "", "due_date": "", "evidence": ""},
            {"content": "", "client_name": "A사", "due_date": "", "evidence": "근거만 있음"},
        ],
    }
    assert normalize_summary(raw)["commitments"] == []


def test_resolve_client_id_matches_existing(client, db_session):
    a = Client(group_id=1, name="A사")
    db_session.add(a)
    db_session.commit()

    assert commitment_service.resolve_client_id(db_session, 1, "A사") == a.id
    assert commitment_service.resolve_client_id(db_session, 1, " A사 ") == a.id


def test_resolve_client_id_returns_none_and_creates_nothing(client, db_session):
    """모델이 언급했다는 이유로 Client를 만들지 않는다 — 환각이 목록을 오염시킨다."""
    assert commitment_service.resolve_client_id(db_session, 1, "듣보사") is None
    assert db_session.query(Client).count() == 0


def test_resolve_client_id_does_not_cross_groups(client, db_session):
    db_session.add(Client(group_id=2, name="A사"))
    db_session.commit()

    assert commitment_service.resolve_client_id(db_session, 1, "A사") is None


def test_create_commitments_stores_proposed(client, db_session):
    a = Client(group_id=1, name="A사")
    db_session.add(a)
    db_session.commit()

    created = commitment_service.create_commitments(
        db_session,
        group_id=1,
        items=[
            {
                "content": "시안 3종 전달",
                "client_name": "A사",
                "due_date": "2026-08-13",
                "evidence": "수요일까지 드릴게요",
            },
            {
                "content": "견적서 발송",
                "client_name": "듣보사",
                "due_date": "",
                "evidence": "견적은 내일 드릴게요",
            },
        ],
        source_type="call",
        source_id=7,
    )
    db_session.commit()

    assert len(created) == 2
    assert created[0].status == "proposed"
    assert created[0].client_id == a.id
    assert created[0].due_date == date(2026, 8, 13)
    assert created[0].source_type == "call"
    assert created[0].source_id == 7
    # 이름을 못 찾은 쪽은 client_id 없이 저장된다
    assert created[1].client_id is None
    assert created[1].due_date is None


def test_create_commitments_with_empty_list(client, db_session):
    assert commitment_service.create_commitments(
        db_session, group_id=1, items=[], source_type="chat", source_id=None
    ) == []
    assert db_session.query(Commitment).count() == 0
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `pytest tests/test_commitment_extraction.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'commitment_service'`

- [ ] **Step 3: Gemini 스키마와 정규화를 고친다**

`gemini_service.py`의 `_SUMMARY_SCHEMA` 바로 위에 항목 스키마를 추가한다 (채팅 스캔에서도 재사용):

```python
_COMMITMENT_ITEM_SCHEMA = {
    "type": "OBJECT",
    "required": ["content", "client_name", "due_date", "evidence"],
    "properties": {
        "content": {"type": "STRING", "description": "약속한 산출물이나 행동."},
        "client_name": {
            "type": "STRING",
            "description": "약속을 받은 상대 회사/담당자명. 특정 못하면 빈 문자열.",
        },
        "due_date": {
            "type": "STRING",
            "description": "YYYY-MM-DD 형식. 기한이 없으면 빈 문자열.",
        },
        "evidence": {
            "type": "STRING",
            "description": "그렇게 판단한 근거가 되는 원문 한 문장. 요약하지 말고 그대로 옮긴다.",
        },
    },
}
```

`_SUMMARY_SCHEMA`의 `required` 배열에 `"commitments"`를 추가하고, `properties`에 추가한다:

```python
        "commitments": {"type": "ARRAY", "items": _COMMITMENT_ITEM_SCHEMA},
```

`CALL_SUMMARY_PROMPT`와 `DOCUMENT_SUMMARY_PROMPT` 양쪽의 필드 설명 목록에 다음 항목을 추가한다:

```
- commitments: 우리 쪽이 상대(고객사)에게 하기로 약속한 것만. action_items와 달리
  내부 작업이 아니라 상대방에게 말한 약속이다. evidence에는 그렇게 판단한 근거
  원문을 한 문장 그대로 옮긴다. "검토해볼게요" 같은 모호한 표현은 넣지 않는다.
  약속이 없으면 빈 배열.
```

`normalize_summary`의 `return` 직전에 약속 정규화를 추가한다:

```python
    commitments = []
    for item in raw.get("commitments") or []:
        if not isinstance(item, dict):
            continue
        content = (item.get("content") or "").strip()
        evidence = (item.get("evidence") or "").strip()
        # 근거 없는 약속은 사람이 확인할 수 없고, 내용 없는 약속은 의미가 없다.
        if not content or not evidence:
            continue
        commitments.append(
            {
                "content": content,
                "client_name": (item.get("client_name") or "").strip(),
                "due_date": (item.get("due_date") or "").strip(),
                "evidence": evidence,
            }
        )
```

그리고 반환 딕셔너리에 `"commitments": commitments,`를 추가한다.

- [ ] **Step 4: commitment_service를 만든다**

`commitment_service.py`:

```python
"""약속 추출 결과를 DB에 반영하는 계층.

라우터와 요약 파이프라인 양쪽에서 쓰이므로 별도 모듈로 둔다.
"""

import logging
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Client, Commitment

logger = logging.getLogger(__name__)


def _parse_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def resolve_client_id(db: Session, group_id: int, client_name: str) -> int | None:
    """모델이 말한 클라이언트명을 등록된 Client와 대조한다.

    없으면 None을 돌려주고 새로 만들지 않는다. 오탈자와 환각이 클라이언트
    목록을 오염시키기 때문이다. 클라이언트 생성은 사람이 한다.
    """
    name = (client_name or "").strip()
    if not name:
        return None
    found = db.execute(
        select(Client).where(Client.group_id == group_id, Client.name == name)
    ).scalar_one_or_none()
    return found.id if found else None


def create_commitments(
    db: Session,
    group_id: int,
    items: list[dict],
    source_type: str,
    source_id: int | None,
) -> list[Commitment]:
    """추출된 약속을 proposed 상태로 저장한다. commit은 호출자가 한다."""
    created: list[Commitment] = []
    for item in items:
        content = (item.get("content") or "").strip()
        evidence = (item.get("evidence") or "").strip()
        if not content or not evidence:
            continue
        commitment = Commitment(
            group_id=group_id,
            client_id=resolve_client_id(db, group_id, item.get("client_name", "")),
            content=content,
            due_date=_parse_date(item.get("due_date") or ""),
            status="proposed",
            source_type=source_type,
            source_id=source_id,
            evidence=evidence,
        )
        db.add(commitment)
        created.append(commitment)
    return created
```

- [ ] **Step 5: 테스트가 통과하는지 확인한다**

Run: `pytest tests/test_commitment_extraction.py -v`
Expected: 8 passed

- [ ] **Step 6: 요약 파이프라인에 연결한다**

`main.py` 상단에 추가한다 (로거가 없으면 함께):

```python
import logging

import commitment_service

logger = logging.getLogger(__name__)
```

`_summarize_and_store`의 할 일 생성 블록 다음, `return` 직전에 추가:

```python
    created_commitments: list = []
    if structured:
        # 약속 추출이 깨져도 요약은 살아야 한다. 요약을 인질로 잡지 않는다.
        try:
            created_commitments = commitment_service.create_commitments(
                db,
                group_id=group_id,
                items=structured.get("commitments") or [],
                source_type=source_type,
                source_id=doc.id,
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.warning(
                "약속 저장 실패",
                extra={"event": "commitment.create.failed", "document_id": doc.id},
                exc_info=True,
            )
            created_commitments = []
```

반환 딕셔너리에 `"created_commitments": len(created_commitments),`를 추가한다.

- [ ] **Step 7: 요약 실패 격리 테스트를 추가하고 통과시킨다**

`tests/test_commitment_extraction.py`에 추가:

```python
def test_summary_survives_commitment_failure(client, db_session, monkeypatch):
    """약속 저장이 터져도 요약 문서는 남아야 한다."""
    import main
    from models import Document

    token = client.post(
        "/api/v1/auth/signup",
        json={"email": "admin@onque.dev", "password": "password123", "name": "관리자"},
    ).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    group = client.post("/api/v1/groups", json={"name": "A팀"}, headers=headers).json()["data"]

    async def fake_summarize(file, prompt):
        return (
            {
                "headline": "요약됨",
                "key_points": [],
                "requests": [],
                "action_items": [],
                "notes": "",
                "commitments": [
                    {"content": "시안 전달", "client_name": "", "due_date": "", "evidence": "드릴게요"}
                ],
            },
            "요약됨",
        )

    def boom(*args, **kwargs):
        raise RuntimeError("DB 폭발")

    monkeypatch.setattr(main.gemini_service, "summarize_upload", fake_summarize)
    monkeypatch.setattr(main.gemini_service, "classify_document_category", lambda t: "기타")
    monkeypatch.setattr(main.commitment_service, "create_commitments", boom)

    res = client.post(
        "/summarize-document",
        params={"group_id": group["id"]},
        files={"file": ("test.txt", b"content", "text/plain")},
        headers=headers,
    )

    assert res.status_code == 200
    assert db_session.query(Document).count() == 1
```

Run: `pytest tests/test_commitment_extraction.py -v`
Expected: 9 passed

Run: `pytest -q`
Expected: 전부 통과

- [ ] **Step 8: 커밋**

```bash
git add gemini_service.py commitment_service.py main.py tests/test_commitment_extraction.py
git commit -m "feat: 요약 파이프라인에서 클라이언트 약속 추출"
```

---

### Task 4: 약속 조회와 상태 변경 API

**Files:**
- Modify: `routers/commitments.py`
- Modify: `commitment_service.py` (상태 전이 규칙, 기한 계산)
- Test: `tests/test_commitment_routes.py`

**Interfaces:**
- Consumes: `models.Commitment` (Task 1), `routers.commitments._ok`·`_require_group_member` (Task 2), `commitment_service` (Task 3)
- Produces:
  - `commitment_service.TERMINAL_STATUSES: frozenset[str]` = `{"fulfilled", "dismissed"}`
  - `commitment_service.DUE_SOON_DAYS: int` = `2`
  - `commitment_service.can_transition(current: str, target: str) -> bool`
  - `commitment_service.apply_status(commitment: Commitment, target: str) -> None`
  - `commitment_service.due_flags(commitment: Commitment, today: date) -> tuple[bool, bool]`
  - `routers.commitments._serialize_commitment(c: Commitment, client_name: str | None, today: date) -> dict` — `{id, content, client_id, client_name, due_date, status, source_type, source_id, evidence, is_overdue, is_due_soon, created_at}`
  - `GET /api/v1/commitments?group_id=&status=&client_id=&limit=`
  - `PATCH /api/v1/commitments/{commitment_id}` body `{status}`
  - `POST /api/v1/commitments/bulk-status` body `{ids: list[int], status: str}`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_commitment_routes.py`:

```python
from datetime import date, timedelta

from models import Client, Commitment


def _setup(client):
    token = client.post(
        "/api/v1/auth/signup",
        json={"email": "admin@onque.dev", "password": "password123", "name": "관리자"},
    ).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    group_a = client.post("/api/v1/groups", json={"name": "A팀"}, headers=headers).json()["data"]
    group_b = client.post("/api/v1/groups", json={"name": "B팀"}, headers=headers).json()["data"]
    return headers, group_a["id"], group_b["id"]


def _seed(db_session, group_id, **kwargs):
    defaults = {
        "group_id": group_id,
        "content": "시안 3종 전달",
        "source_type": "call",
        "evidence": "수요일까지 드릴게요",
    }
    defaults.update(kwargs)
    c = Commitment(**defaults)
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


def test_list_returns_client_name(client, db_session):
    headers, group_a, _ = _setup(client)
    a = Client(group_id=group_a, name="A사")
    db_session.add(a)
    db_session.commit()
    _seed(db_session, group_a, client_id=a.id)

    res = client.get("/api/v1/commitments", params={"group_id": group_a}, headers=headers)
    data = res.json()["data"]
    assert len(data) == 1
    assert data[0]["client_name"] == "A사"
    assert data[0]["status"] == "proposed"


def test_list_filters_by_status(client, db_session):
    headers, group_a, _ = _setup(client)
    _seed(db_session, group_a, content="제안된 것")
    _seed(db_session, group_a, content="확정된 것", status="confirmed")

    res = client.get(
        "/api/v1/commitments",
        params={"group_id": group_a, "status": "proposed"},
        headers=headers,
    )
    assert [c["content"] for c in res.json()["data"]] == ["제안된 것"]


def test_list_isolated_between_groups(client, db_session):
    headers, group_a, group_b = _setup(client)
    _seed(db_session, group_b, content="B팀 약속")

    res = client.get("/api/v1/commitments", params={"group_id": group_a}, headers=headers)
    assert res.json()["data"] == []


def test_list_rejects_limit_over_100(client, db_session):
    headers, group_a, _ = _setup(client)
    res = client.get(
        "/api/v1/commitments", params={"group_id": group_a, "limit": 500}, headers=headers
    )
    assert res.status_code == 422


def test_due_soon_and_overdue_are_computed(client, db_session):
    headers, group_a, _ = _setup(client)
    today = date.today()
    _seed(
        db_session, group_a, content="지남", status="confirmed",
        due_date=today - timedelta(days=1),
    )
    _seed(
        db_session, group_a, content="임박", status="confirmed",
        due_date=today + timedelta(days=1),
    )
    _seed(
        db_session, group_a, content="여유", status="confirmed",
        due_date=today + timedelta(days=30),
    )
    # proposed는 아직 추적 대상이 아니므로 경고하지 않는다
    _seed(db_session, group_a, content="제안", due_date=today - timedelta(days=5))

    data = client.get(
        "/api/v1/commitments", params={"group_id": group_a}, headers=headers
    ).json()["data"]
    by_content = {c["content"]: c for c in data}

    assert by_content["지남"]["is_overdue"] is True
    assert by_content["임박"]["is_due_soon"] is True
    assert by_content["여유"]["is_due_soon"] is False
    assert by_content["제안"]["is_overdue"] is False


def test_patch_confirms_commitment(client, db_session):
    headers, group_a, _ = _setup(client)
    c = _seed(db_session, group_a)

    res = client.patch(
        f"/api/v1/commitments/{c.id}", json={"status": "confirmed"}, headers=headers
    )
    assert res.status_code == 200
    assert res.json()["data"]["status"] == "confirmed"

    db_session.expire_all()
    assert db_session.get(Commitment, c.id).confirmed_at is not None


def test_patch_rejects_transition_from_terminal_status(client, db_session):
    headers, group_a, _ = _setup(client)
    c = _seed(db_session, group_a, status="dismissed")

    res = client.patch(
        f"/api/v1/commitments/{c.id}", json={"status": "confirmed"}, headers=headers
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "COMMITMENT_STATUS_INVALID"


def test_patch_rejects_unknown_status(client, db_session):
    headers, group_a, _ = _setup(client)
    c = _seed(db_session, group_a)

    res = client.patch(
        f"/api/v1/commitments/{c.id}", json={"status": "잘못된값"}, headers=headers
    )
    assert res.status_code == 400


def test_patch_rejects_cross_group(client, db_session):
    headers, group_a, _ = _setup(client)
    other = client.post(
        "/api/v1/auth/signup",
        json={"email": "other@onque.dev", "password": "password123", "name": "외부인"},
    ).json()["data"]["token"]
    c = _seed(db_session, group_a)

    res = client.patch(
        f"/api/v1/commitments/{c.id}",
        json={"status": "confirmed"},
        headers={"Authorization": f"Bearer {other}"},
    )
    assert res.status_code == 403


def test_bulk_status_confirms_many(client, db_session):
    headers, group_a, _ = _setup(client)
    a = _seed(db_session, group_a, content="첫째")
    b = _seed(db_session, group_a, content="둘째")

    res = client.post(
        "/api/v1/commitments/bulk-status",
        json={"ids": [a.id, b.id], "status": "confirmed"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["data"]["updated"] == 2

    db_session.expire_all()
    assert db_session.get(Commitment, a.id).status == "confirmed"
    assert db_session.get(Commitment, b.id).status == "confirmed"


def test_bulk_status_rejects_all_if_one_is_foreign(client, db_session):
    """부분 성공은 사용자가 무엇이 반영됐는지 알 수 없게 만든다. 전부 거부한다."""
    headers, group_a, group_b = _setup(client)
    mine = _seed(db_session, group_a, content="내 것")
    theirs = _seed(db_session, group_b, content="남의 것")

    res = client.post(
        "/api/v1/commitments/bulk-status",
        json={"ids": [mine.id, theirs.id], "status": "dismissed"},
        headers=headers,
    )
    assert res.status_code == 403

    db_session.expire_all()
    assert db_session.get(Commitment, mine.id).status == "proposed"
```

주의: `test_bulk_status_rejects_all_if_one_is_foreign`은 관리자가 두 그룹 모두의 멤버인 상태라 403이 나지 않는다. `_setup`이 만든 관리자는 A팀·B팀 양쪽 소속이다. 이 테스트에서는 **B팀 약속을 관리자가 아닌 다른 그룹**으로 만들어야 한다. `_setup`에서 만든 `group_b` 대신, 다른 사용자가 만든 그룹을 쓰도록 아래처럼 고친다:

```python
def test_bulk_status_rejects_all_if_one_is_foreign(client, db_session):
    """부분 성공은 사용자가 무엇이 반영됐는지 알 수 없게 만든다. 전부 거부한다."""
    headers, group_a, _ = _setup(client)
    outsider = client.post(
        "/api/v1/auth/signup",
        json={"email": "out@onque.dev", "password": "password123", "name": "외부인"},
    ).json()["data"]["token"]
    foreign_group = client.post(
        "/api/v1/groups",
        json={"name": "외부팀"},
        headers={"Authorization": f"Bearer {outsider}"},
    ).json()["data"]["id"]

    mine = _seed(db_session, group_a, content="내 것")
    theirs = _seed(db_session, foreign_group, content="남의 것")

    res = client.post(
        "/api/v1/commitments/bulk-status",
        json={"ids": [mine.id, theirs.id], "status": "dismissed"},
        headers=headers,
    )
    assert res.status_code == 403

    db_session.expire_all()
    assert db_session.get(Commitment, mine.id).status == "proposed"
```

`test_list_isolated_between_groups`는 조회 필터가 `group_id`로 걸리므로 그대로 둬도 된다.

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `pytest tests/test_commitment_routes.py -v`
Expected: FAIL — 404 / 405

- [ ] **Step 3: 상태 전이와 기한 계산을 구현한다**

`commitment_service.py`의 import를 고친다:

```python
from datetime import date, datetime, timezone
```

그리고 `from models import Client, Commitment` 를 `from models import Client, Commitment, COMMITMENT_STATUSES` 로 바꾼다.

본문에 추가:

```python
TERMINAL_STATUSES = frozenset({"fulfilled", "dismissed"})

# 기한 경고 기준. D-2 이내면 임박으로 본다.
DUE_SOON_DAYS = 2


def can_transition(current: str, target: str) -> bool:
    """종료 상태에서는 빠져나오지 못한다. 잘못 눌렀다면 새 약속을 만든다."""
    if target not in COMMITMENT_STATUSES:
        return False
    if current in TERMINAL_STATUSES:
        return False
    return current != target


def apply_status(commitment: Commitment, target: str) -> None:
    commitment.status = target
    if target == "confirmed" and commitment.confirmed_at is None:
        commitment.confirmed_at = datetime.now(timezone.utc)


def due_flags(commitment: Commitment, today: date) -> tuple[bool, bool]:
    """(is_overdue, is_due_soon). 저장하지 않고 조회 시 계산하는 파생값이다.

    proposed 상태는 아직 사람이 확인하지 않았으므로 추적 대상이 아니다.
    """
    if commitment.status != "confirmed" or commitment.due_date is None:
        return (False, False)
    delta = (commitment.due_date - today).days
    return (delta < 0, 0 <= delta <= DUE_SOON_DAYS)
```

- [ ] **Step 4: 라우터에 엔드포인트를 추가한다**

`routers/commitments.py`의 import에 추가:

```python
from datetime import date as date_type

import commitment_service
from models import Commitment
```

본문에 추가 (`bulk-status`를 `{commitment_id}`보다 먼저 정의한다):

```python
def _serialize_commitment(c: Commitment, client_name: str | None, today: date_type) -> dict:
    is_overdue, is_due_soon = commitment_service.due_flags(c, today)
    return {
        "id": c.id,
        "content": c.content,
        "client_id": c.client_id,
        "client_name": client_name,
        "due_date": c.due_date.isoformat() if c.due_date else None,
        "status": c.status,
        "source_type": c.source_type,
        "source_id": c.source_id,
        "evidence": c.evidence,
        "is_overdue": is_overdue,
        "is_due_soon": is_due_soon,
        "created_at": c.created_at.isoformat(),
    }


class StatusBody(BaseModel):
    status: str


class BulkStatusBody(BaseModel):
    ids: list[int]
    status: str


def _client_name(db: Session, client_id: int | None) -> str | None:
    if client_id is None:
        return None
    linked = db.get(Client, client_id)
    return linked.name if linked else None


@router.get("/commitments")
def list_commitments(
    group_id: int,
    status: str | None = None,
    client_id: int | None = None,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_group_member(current_user, group_id, db)

    query = select(Commitment).where(Commitment.group_id == group_id)
    if status is not None:
        query = query.where(Commitment.status == status)
    if client_id is not None:
        query = query.where(Commitment.client_id == client_id)
    rows = db.execute(
        query.order_by(Commitment.created_at.desc()).limit(limit)
    ).scalars().all()

    names = {
        c.id: c.name
        for c in db.execute(select(Client).where(Client.group_id == group_id))
        .scalars()
        .all()
    }
    today = date_type.today()
    return _ok([_serialize_commitment(c, names.get(c.client_id), today) for c in rows])


@router.post("/commitments/bulk-status")
def bulk_update_status(
    body: BulkStatusBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not body.ids:
        return _ok({"updated": 0})

    rows = db.execute(
        select(Commitment).where(Commitment.id.in_(body.ids))
    ).scalars().all()
    if len(rows) != len(set(body.ids)):
        raise HTTPException(
            status_code=404,
            detail={"code": "COMMITMENT_NOT_FOUND", "message": "약속을 찾을 수 없습니다"},
        )

    # 부분 성공은 무엇이 반영됐는지 알 수 없게 만든다. 하나라도 남의 것이면 전부 거부한다.
    for row in rows:
        _require_group_member(current_user, row.group_id, db)
    for row in rows:
        if not commitment_service.can_transition(row.status, body.status):
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "COMMITMENT_STATUS_INVALID",
                    "message": f"{row.status}에서 {body.status}로 바꿀 수 없습니다",
                },
            )

    for row in rows:
        commitment_service.apply_status(row, body.status)
    db.commit()
    return _ok({"updated": len(rows)})


@router.patch("/commitments/{commitment_id}")
def update_commitment_status(
    commitment_id: int,
    body: StatusBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    found = db.get(Commitment, commitment_id)
    if found is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "COMMITMENT_NOT_FOUND", "message": "약속을 찾을 수 없습니다"},
        )
    _require_group_member(current_user, found.group_id, db)

    if not commitment_service.can_transition(found.status, body.status):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "COMMITMENT_STATUS_INVALID",
                "message": f"{found.status}에서 {body.status}로 바꿀 수 없습니다",
            },
        )
    commitment_service.apply_status(found, body.status)
    db.commit()
    db.refresh(found)
    return _ok(_serialize_commitment(found, _client_name(db, found.client_id), date_type.today()))
```

- [ ] **Step 5: 테스트가 통과하는지 확인한다**

Run: `pytest tests/test_commitment_routes.py -v`
Expected: 11 passed

Run: `pytest -q`
Expected: 전부 통과

- [ ] **Step 6: 커밋**

```bash
git add routers/commitments.py commitment_service.py tests/test_commitment_routes.py
git commit -m "feat: 약속 조회/상태 변경 API와 기한 계산"
```

---

### Task 5: 채팅 배치 스캔과 요청 편승 스윕

**Files:**
- Modify: `gemini_service.py` (채팅 약속 추출 함수)
- Modify: `commitment_service.py` (스윕 로직)
- Modify: `routers/commitments.py` (`list_commitments`에 스윕 호출)
- Test: `tests/test_commitment_sweep.py`

**Interfaces:**
- Consumes: `commitment_service.create_commitments` (Task 3), `models.ChatRoom.last_scanned_message_id`·`models.Group.last_swept_at` (Task 1), `gemini_service._COMMITMENT_ITEM_SCHEMA` (Task 3)
- Produces:
  - `gemini_service.extract_chat_commitments(history_text: str) -> list[dict]` — 실패 시 빈 리스트
  - `commitment_service.SWEEP_COOLDOWN_MINUTES: int` = `10`
  - `commitment_service.CHAT_SCAN_THRESHOLD: int` = `15`
  - `commitment_service.maybe_sweep(db: Session, group_id: int) -> int` — 스캔한 방 수

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_commitment_sweep.py`:

```python
from datetime import datetime, timedelta, timezone

import commitment_service
from models import ChatMessage, ChatRoom, Commitment, Group


def _make_room(db_session, group_id, message_count):
    room = ChatRoom(group_id=group_id, name="A사 방")
    db_session.add(room)
    db_session.commit()
    db_session.refresh(room)
    for i in range(message_count):
        db_session.add(
            ChatMessage(
                group_id=group_id,
                room_id=room.id,
                sender="김담당",
                content=f"메시지 {i}",
            )
        )
    db_session.commit()
    return room


def _stub_extractor(monkeypatch, items):
    monkeypatch.setattr(
        commitment_service.gemini_service,
        "extract_chat_commitments",
        lambda text: items,
    )


_SAMPLE = [{"content": "시안 전달", "client_name": "", "due_date": "", "evidence": "드릴게요"}]


def test_sweep_skips_room_below_threshold(client, db_session, monkeypatch):
    group = Group(name="A팀")
    db_session.add(group)
    db_session.commit()
    _make_room(db_session, group.id, message_count=14)
    _stub_extractor(monkeypatch, _SAMPLE)

    scanned = commitment_service.maybe_sweep(db_session, group.id)

    assert scanned == 0
    assert db_session.query(Commitment).count() == 0


def test_sweep_scans_room_at_threshold(client, db_session, monkeypatch):
    group = Group(name="A팀")
    db_session.add(group)
    db_session.commit()
    room = _make_room(db_session, group.id, message_count=15)
    _stub_extractor(monkeypatch, _SAMPLE)

    scanned = commitment_service.maybe_sweep(db_session, group.id)

    assert scanned == 1
    saved = db_session.query(Commitment).all()
    assert len(saved) == 1
    assert saved[0].source_type == "chat"
    assert saved[0].status == "proposed"

    db_session.refresh(room)
    assert room.last_scanned_message_id is not None


def test_sweep_respects_cooldown(client, db_session, monkeypatch):
    group = Group(name="A팀", last_swept_at=datetime.now(timezone.utc))
    db_session.add(group)
    db_session.commit()
    _make_room(db_session, group.id, message_count=20)
    _stub_extractor(monkeypatch, _SAMPLE)

    assert commitment_service.maybe_sweep(db_session, group.id) == 0
    assert db_session.query(Commitment).count() == 0


def test_sweep_runs_after_cooldown_expires(client, db_session, monkeypatch):
    stale = datetime.now(timezone.utc) - timedelta(
        minutes=commitment_service.SWEEP_COOLDOWN_MINUTES + 1
    )
    group = Group(name="A팀", last_swept_at=stale)
    db_session.add(group)
    db_session.commit()
    _make_room(db_session, group.id, message_count=20)
    _stub_extractor(monkeypatch, _SAMPLE)

    assert commitment_service.maybe_sweep(db_session, group.id) == 1


def test_second_sweep_does_not_rescan_same_messages(client, db_session, monkeypatch):
    group = Group(name="A팀")
    db_session.add(group)
    db_session.commit()
    _make_room(db_session, group.id, message_count=20)
    _stub_extractor(monkeypatch, _SAMPLE)

    commitment_service.maybe_sweep(db_session, group.id)
    # 쿨다운을 강제로 만료시켜 두 번째 스윕을 허용한다
    group.last_swept_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.commit()

    assert commitment_service.maybe_sweep(db_session, group.id) == 0
    assert db_session.query(Commitment).count() == 1


def test_sweep_failure_does_not_raise(client, db_session, monkeypatch):
    """스윕은 부가 작업이다. 터져도 조회 요청을 실패시키지 않는다."""
    group = Group(name="A팀")
    db_session.add(group)
    db_session.commit()
    _make_room(db_session, group.id, message_count=20)

    def boom(text):
        raise RuntimeError("모델 폭발")

    monkeypatch.setattr(commitment_service.gemini_service, "extract_chat_commitments", boom)

    assert commitment_service.maybe_sweep(db_session, group.id) == 0
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `pytest tests/test_commitment_sweep.py -v`
Expected: FAIL — `AttributeError: module 'commitment_service' has no attribute 'maybe_sweep'`

- [ ] **Step 3: Gemini 채팅 추출 함수를 추가한다**

`gemini_service.py`에 추가 (`_COMMITMENT_ITEM_SCHEMA` 정의 이후 아무 곳):

```python
_CHAT_COMMITMENT_SCHEMA = {
    "type": "OBJECT",
    "required": ["commitments"],
    "properties": {
        "commitments": {"type": "ARRAY", "items": _COMMITMENT_ITEM_SCHEMA},
    },
}

_CHAT_COMMITMENT_PROMPT = """
너는 대행사 팀 채팅을 지켜보는 비서다.
아래 [대화]에서 우리 쪽이 고객사에게 하기로 약속한 것만 뽑아라.

규칙:
- 내부 업무 분담이나 팀원끼리의 다짐은 약속이 아니다. 상대(고객사)에게 말한 것만.
- "검토해볼게요", "확인해보겠습니다" 같은 모호한 표현은 넣지 않는다.
  산출물이나 행동이 특정되는 것만 넣는다.
- evidence에는 그렇게 판단한 근거가 되는 대화 원문 한 줄을 그대로 옮긴다. 요약하지 않는다.
- 날짜는 위에 주어진 오늘 날짜를 기준으로 YYYY-MM-DD 절대 날짜로 변환한다.
  기한이 없으면 빈 문자열.
- 약속이 없으면 빈 배열을 돌려준다. 억지로 만들지 않는다.
- 이모지, 서론, 마크다운 기호를 쓰지 말 것.
"""


def extract_chat_commitments(history_text: str) -> list[dict]:
    """대화 이력에서 고객사 약속을 뽑는다. 실패 시 빈 리스트.

    스윕은 부가 작업이라 여기서 예외를 밖으로 던지지 않는다.
    extract_chat_actions와 같은 방침.
    """
    prompt = (
        f"{korean_date_context()}\n\n{_CHAT_COMMITMENT_PROMPT}\n\n[대화]\n{history_text}"
    )
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_CHAT_COMMITMENT_SCHEMA,
            ),
        )
        data = json.loads(response.text)
        return data.get("commitments") or []
    except Exception:
        return []
```

- [ ] **Step 4: 스윕을 구현한다**

`commitment_service.py`의 import를 고친다:

```python
from datetime import date, datetime, timedelta, timezone

import gemini_service
from models import ChatMessage, ChatRoom, Client, Commitment, Group, COMMITMENT_STATUSES
```

본문에 추가:

```python
SWEEP_COOLDOWN_MINUTES = 10
# 이보다 적게 쌓인 방은 훑지 않는다. 한산한 방은 영영 안 훑일 수 있으나,
# 그런 방에서 놓칠 약속은 적고 사용자는 명령어로 직접 부를 수 있다.
CHAT_SCAN_THRESHOLD = 15


def _scan_room(db: Session, room: ChatRoom) -> bool:
    """방 하나를 훑는다. 실제로 스캔했으면 True."""
    query = select(ChatMessage).where(ChatMessage.room_id == room.id)
    if room.last_scanned_message_id is not None:
        query = query.where(ChatMessage.id > room.last_scanned_message_id)
    messages = db.execute(query.order_by(ChatMessage.id)).scalars().all()

    if len(messages) < CHAT_SCAN_THRESHOLD:
        return False

    history = "\n".join(f"{m.sender}: {m.content}" for m in messages)
    items = gemini_service.extract_chat_commitments(history)
    create_commitments(
        db,
        group_id=room.group_id,
        items=items,
        source_type="chat",
        source_id=messages[-1].id,
    )
    room.last_scanned_message_id = messages[-1].id
    return True


def maybe_sweep(db: Session, group_id: int) -> int:
    """요청에 편승해 돌리는 자율 점검. 스캔한 방 수를 돌려준다.

    Render 무료 티어에 상주 워커가 없어 백그라운드 스케줄러를 쓸 수 없다.
    아무도 접속하지 않으면 스윕도 안 돌지만, 그때는 알림을 볼 사람도 없다.
    """
    group = db.get(Group, group_id)
    if group is None:
        return 0

    now = datetime.now(timezone.utc)
    if group.last_swept_at is not None:
        last = group.last_swept_at
        # SQLite는 tz 정보를 잃어버린다. UTC로 간주하고 비교한다.
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if now - last < timedelta(minutes=SWEEP_COOLDOWN_MINUTES):
            return 0

    scanned = 0
    try:
        rooms = db.execute(
            select(ChatRoom).where(ChatRoom.group_id == group_id)
        ).scalars().all()
        for room in rooms:
            if _scan_room(db, room):
                scanned += 1
        group.last_swept_at = now
        db.commit()
    except Exception:
        db.rollback()
        logger.warning(
            "스윕 실패",
            extra={"event": "commitment.sweep.failed", "group_id": group_id},
            exc_info=True,
        )
        return 0

    return scanned
```

- [ ] **Step 5: 테스트가 통과하는지 확인한다**

Run: `pytest tests/test_commitment_sweep.py -v`
Expected: 6 passed

- [ ] **Step 6: 조회 엔드포인트에 스윕을 편승시킨다**

`routers/commitments.py`의 `list_commitments`에서 `_require_group_member(current_user, group_id, db)` 바로 다음 줄에 추가:

```python
    commitment_service.maybe_sweep(db, group_id)
```

- [ ] **Step 7: 편승 동작 테스트를 추가하고 통과시킨다**

`tests/test_commitment_sweep.py`에 추가:

```python
def test_list_endpoint_triggers_sweep(client, db_session, monkeypatch):
    token = client.post(
        "/api/v1/auth/signup",
        json={"email": "admin@onque.dev", "password": "password123", "name": "관리자"},
    ).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    group = client.post("/api/v1/groups", json={"name": "A팀"}, headers=headers).json()["data"]

    _make_room(db_session, group["id"], message_count=20)
    _stub_extractor(monkeypatch, _SAMPLE)

    res = client.get("/api/v1/commitments", params={"group_id": group["id"]}, headers=headers)

    assert res.status_code == 200
    assert [c["content"] for c in res.json()["data"]] == ["시안 전달"]
```

Run: `pytest tests/test_commitment_sweep.py -v`
Expected: 7 passed

Run: `pytest -q`
Expected: 전부 통과

- [ ] **Step 8: 커밋**

```bash
git add gemini_service.py commitment_service.py routers/commitments.py tests/test_commitment_sweep.py
git commit -m "feat: 채팅 배치 스캔과 요청 편승 스윕"
```

---

### Task 6: 프론트엔드 "확인 필요" 카드

**Files:**
- Modify: `onque-frontend/lib/api.ts`
- Create: `onque-frontend/components/CommitmentPanel.tsx`
- Modify: `onque-frontend/app/dashboard/page.tsx`

**Interfaces:**
- Consumes: Task 2·4·5의 엔드포인트
- Produces:
  - `lib/api.ts`: `CommitmentRecord` 타입, `getCommitments(groupId, status?)`, `bulkUpdateCommitments(ids, status)`
  - `components/CommitmentPanel.tsx`: `export default function CommitmentPanel({ groupId }: { groupId: number })`

- [ ] **Step 1: API 클라이언트에 타입과 함수를 추가한다**

`onque-frontend/lib/api.ts`의 타입 정의 구역(다른 `export type` 옆)에 추가:

```ts
export type CommitmentRecord = {
  id: number;
  content: string;
  client_id: number | null;
  client_name: string | null;
  due_date: string | null;
  status: 'proposed' | 'confirmed' | 'fulfilled' | 'dismissed';
  source_type: 'call' | 'document' | 'chat';
  source_id: number | null;
  evidence: string;
  is_overdue: boolean;
  is_due_soon: boolean;
  created_at: string;
};
```

함수 구역에 추가. `/api/v1` 라우터는 envelope를 돌려주므로 `requestEnveloped`를 쓴다:

```ts
export function getCommitments(
  groupId: number,
  status?: CommitmentRecord['status'],
): Promise<CommitmentRecord[]> {
  const params = new URLSearchParams({ group_id: String(groupId) });
  if (status) params.set('status', status);
  return requestEnveloped<CommitmentRecord[]>(`/api/v1/commitments?${params}`);
}

export function bulkUpdateCommitments(
  ids: number[],
  status: CommitmentRecord['status'],
): Promise<{ updated: number }> {
  return requestEnveloped<{ updated: number }>('/api/v1/commitments/bulk-status', {
    method: 'POST',
    body: JSON.stringify({ ids, status }),
  });
}
```

- [ ] **Step 2: 패널 컴포넌트를 만든다**

`onque-frontend/components/CommitmentPanel.tsx`:

```tsx
'use client';

import { useCallback, useEffect, useState } from 'react';

import {
  bulkUpdateCommitments,
  getCommitments,
  type CommitmentRecord,
} from '@/lib/api';

const SOURCE_LABEL: Record<CommitmentRecord['source_type'], string> = {
  call: '통화',
  document: '문서',
  chat: '채팅',
};

export default function CommitmentPanel({ groupId }: { groupId: number }) {
  const [proposed, setProposed] = useState<CommitmentRecord[]>([]);
  const [tracked, setTracked] = useState<CommitmentRecord[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      // 조회가 스윕을 겸한다. proposed를 먼저 불러야 갓 추출된 항목이 반영된다.
      const fresh = await getCommitments(groupId, 'proposed');
      const confirmed = await getCommitments(groupId, 'confirmed');
      setProposed(fresh);
      setTracked(confirmed.filter((c) => c.is_overdue || c.is_due_soon));
      setSelected(new Set());
    } catch (e) {
      setError(e instanceof Error ? e.message : '약속을 불러오지 못했습니다.');
    } finally {
      setIsLoading(false);
    }
  }, [groupId]);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const apply = async (status: 'confirmed' | 'dismissed') => {
    if (selected.size === 0) return;
    try {
      await bulkUpdateCommitments([...selected], status);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : '처리에 실패했습니다.');
    }
  };

  if (isLoading) {
    return (
      <section className="rounded-xl border border-border bg-surface p-6">
        <p className="text-sm text-foreground/50">약속을 확인하는 중입니다</p>
      </section>
    );
  }

  return (
    <section className="rounded-xl border border-border bg-surface p-6">
      <header className="flex items-baseline justify-between">
        <h2 className="text-sm font-bold text-foreground">확인 필요</h2>
        <span className="font-mono text-xs text-foreground/40">{proposed.length}건</span>
      </header>

      {error && <p className="mt-3 text-xs text-accent">{error}</p>}

      {tracked.length > 0 && (
        <div className="mt-4 rounded-lg border border-accent/40 bg-accent/5 p-3">
          <p className="text-xs font-semibold text-accent">기한 주의</p>
          <ul className="mt-2 space-y-1">
            {tracked.map((c) => (
              <li key={c.id} className="text-xs text-foreground/70">
                {c.client_name ?? '미지정'} — {c.content}
                <span className="ml-2 font-mono text-foreground/40">
                  {c.is_overdue ? '기한 초과' : `${c.due_date}까지`}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {proposed.length === 0 ? (
        <p className="mt-4 text-xs text-foreground/40">확인할 약속이 없습니다.</p>
      ) : (
        <>
          <ul className="mt-4 space-y-2">
            {proposed.map((c) => (
              <li
                key={c.id}
                className="rounded-lg border border-border bg-background/40 p-3 transition hover:border-brand/40"
              >
                <label className="flex cursor-pointer items-start gap-3">
                  <input
                    type="checkbox"
                    checked={selected.has(c.id)}
                    onChange={() => toggle(c.id)}
                    className="mt-1 accent-[var(--brand)]"
                  />
                  <span className="flex-1">
                    <span className="block text-sm font-semibold text-foreground">
                      {c.content}
                    </span>
                    <span className="mt-1 block font-mono text-[11px] text-foreground/40">
                      {c.client_name ?? '클라이언트 미지정'}
                      {c.due_date ? ` · ${c.due_date}까지` : ' · 기한 없음'}
                      {` · ${SOURCE_LABEL[c.source_type]}`}
                    </span>
                    <span className="mt-2 block border-l-2 border-border pl-2 text-xs italic text-foreground/50">
                      {c.evidence}
                    </span>
                  </span>
                </label>
              </li>
            ))}
          </ul>

          <div className="mt-4 flex gap-2">
            <button
              type="button"
              onClick={() => apply('confirmed')}
              disabled={selected.size === 0}
              className="rounded-lg bg-brand px-4 py-2 text-xs font-semibold text-brand-foreground transition hover:brightness-110 disabled:opacity-30"
            >
              확정 {selected.size > 0 && `(${selected.size})`}
            </button>
            <button
              type="button"
              onClick={() => apply('dismissed')}
              disabled={selected.size === 0}
              className="rounded-lg border border-border px-4 py-2 text-xs font-semibold text-foreground/70 transition hover:bg-foreground/5 disabled:opacity-30"
            >
              무시
            </button>
          </div>
        </>
      )}
    </section>
  );
}
```

- [ ] **Step 3: 대시보드에 삽입한다**

`onque-frontend/app/dashboard/page.tsx`를 읽어 기존 패널 배치 구조와 활성 그룹 id를 얻는 경로(`WorkspaceContext`)를 확인한다. 다른 패널이 쓰는 것과 같은 방식으로 `groupId`를 얻어 렌더한다.

import를 파일 상단에 추가:

```tsx
import CommitmentPanel from '@/components/CommitmentPanel';
```

기존 패널 목록의 첫 번째 위치에 렌더한다 (확인이 필요한 항목이 가장 먼저 보여야 한다):

```tsx
<CommitmentPanel groupId={groupId} />
```

- [ ] **Step 4: 타입 체크와 빌드를 돌린다**

```bash
cd onque-frontend && npm run build
```
Expected: 타입 에러 없이 빌드 성공

- [ ] **Step 5: 로컬에서 눈으로 확인한다**

백엔드:
```bash
uvicorn main:app --reload
```
프론트:
```bash
cd onque-frontend && npm run dev
```
로그인 후 대시보드에서 "확인 필요" 카드가 렌더되는지 본다. 약속이 없으면 "확인할 약속이 없습니다."가 보여야 한다.

- [ ] **Step 6: 커밋**

`onque-frontend/`는 별도 git 저장소다. 그 안에서 커밋한다.

```bash
cd onque-frontend
git add lib/api.ts components/CommitmentPanel.tsx app/dashboard/page.tsx
git commit -m "feat: 약속 확인 필요 카드"
```

---

### Task 7: 마이그레이션 실행과 배포 확인

**Files:** 없음 (운영 작업)

**Interfaces:**
- Consumes: Task 1~6 전부

- [ ] **Step 1: 전체 테스트를 돌린다**

Run: `pytest -q`
Expected: 전부 통과

- [ ] **Step 2: 백엔드를 푸시한다**

```bash
git pull --rebase
git push origin main
```

Render가 자동 재배포하며 `Base.metadata.create_all`이 `clients`·`commitments` 테이블을 만든다.

- [ ] **Step 3: 배포 완료를 확인한다**

```bash
curl -s https://onque-backend-la7e.onrender.com/openapi.json | grep -o '/api/v1/commitments'
```
Expected: `/api/v1/commitments` 출력

무료 티어 콜드 스타트로 첫 요청이 30~60초 걸릴 수 있다. 응답이 이상하면 상태 코드만 보지 말고 **본문을 확인한다** — TS-017에 남의 서비스 응답을 자기 것으로 오인한 사례가 기록되어 있다.

- [ ] **Step 4: 컬럼 마이그레이션을 실행한다**

`create_all`은 기존 테이블에 컬럼을 추가하지 않는다. Render 셸에서:

```bash
python scripts/migrate_add_commitments.py
```
Expected:
```
chat_rooms.last_scanned_message_id 추가
groups.last_swept_at 추가
```

- [ ] **Step 5: 실제로 동작하는지 확인한다**

배포된 프론트(`https://onque-frontend.vercel.app`)에 로그인해 대시보드를 연다. "확인 필요" 카드가 에러 없이 뜨는지 본다. 이 시점에 스윕이 한 번 돌므로, 메시지 15개 이상 쌓인 방이 있으면 약속이 추출되어 나타난다.

- [ ] **Step 6: 프론트엔드를 푸시한다**

```bash
cd onque-frontend
git pull --rebase
git push
```

Vercel 배포 반영이 늦으면 TS-017 기록을 참고한다.

---

## 자체 검토 결과

**스펙 커버리지**

| 스펙 요구 | 담당 Task |
|---|---|
| Client/Commitment 테이블 | 1 |
| CheckConstraint로 status·source_type 강제 | 1 |
| `ChatRoom.last_scanned_message_id`, `Group.last_swept_at` | 1 |
| 클라이언트 CRUD | 2 |
| 요약 스키마에 `commitments[]` 추가 (추가 호출 없음) | 3 |
| `client_name` 해석, 자동 생성 금지 | 3 |
| 추출 실패가 요약을 실패시키지 않음 | 3 |
| 조회/상태변경/일괄처리 API + 에러 코드 | 4 |
| 기한 경고를 저장하지 않고 계산 | 4 |
| 종료 상태 전이 금지 | 4 |
| 채팅 배치 스캔 (임계값 15) | 5 |
| 요청 편승 스윕 (쿨다운 10분) | 5 |
| 스윕 실패가 조회를 실패시키지 않음 | 5 |
| "확인 필요" 카드, 기한 배너, 이모지 금지 | 6 |

**스펙에 없어 추가한 것**: 마이그레이션 스크립트(Task 1 Step 5)와 실행 절차(Task 7 Step 4). Alembic이 없어 `create_all`이 기존 테이블 컬럼을 추가하지 않기 때문이며, 빠뜨리면 배포 후 런타임에 터진다.

**스펙에서 미룬 것**: 클라이언트별 약속 뷰(스펙 "화면" 3번째 항목)는 Task 6에 넣지 않았다. `GET /commitments?client_id=`가 Task 4에 있어 API는 준비되어 있고, 화면은 "확인 필요" 카드가 실제로 쓸 만한지 확인한 뒤 붙이는 편이 낫다.

**타입 일관성 확인**: `create_commitments`의 시그니처는 Task 3에서 정의하고 Task 5의 `_scan_room`이 동일하게 호출한다. `_serialize_commitment(c, client_name, today)`는 Task 4에서 정의해 같은 Task 안에서만 쓰인다. `_COMMITMENT_ITEM_SCHEMA`는 Task 3에서 정의하고 Task 5의 `_CHAT_COMMITMENT_SCHEMA`가 재사용한다.
