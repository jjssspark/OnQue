# 그룹/워크스페이스 구조 + 최소 인증 Implementation Plan


**Goal:** OnQue를 로그인 없는 단일 전역 워크스페이스에서, 이메일/비밀번호 로그인 + 부서별 그룹으로 데이터가 분리되는 워크스페이스로 바꾼다.

**Architecture:** FastAPI 백엔드에 `User`/`Group`/`GroupMembership`/`Announcement` 테이블과 JWT 기반 인증을 추가하고, 기존 `Todo`/`ChatMessage`/`Schedule`/`Document`에 `group_id`를 붙여 그룹 단위로 스코핑한다. Next.js 프론트는 로그인 페이지 + `AuthContext`(로그인 상태) + `WorkspaceContext` 확장(현재 그룹)으로 그룹 전환 UI를 붙인다.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, PostgreSQL(Neon)/SQLite(테스트), `bcrypt`(비밀번호 해시), `PyJWT`(토큰), `pytest`+`httpx`(백엔드 테스트), Next.js 16 App Router, React Context.

## Global Constraints

- API 응답은 `api-contract.md`의 envelope 형식(`{success, data, error}`)을 따른다.
- 인증 토큰은 `Authorization: Bearer <token>` 헤더로만 받는다. 쿼리 파라미터로 받지 않는다.
- 에러 코드는 `{도메인}_{대상}_{사유}` SCREAMING_SNAKE_CASE.
- 비밀값(`JWT_SECRET` 등)은 `.env`에만 두고 `.env.example`에 더미값으로 문서화한다.
- 이번 스펙 범위는 그룹/인증 구조까지다. 채팅 UI 리디자인, 에이전틱 자동화, 대행업체 특화 업무 모델은 다음 스펙에서 다룬다 (설계 문서 `docs/specs/2026-08-05-group-workspace-auth-design.md` 참고).
- JWT는 프론트 `localStorage`에 저장한다 — `react/security.md`는 세션을 `localStorage`에 두지 말라고 하지만(XSS 노출), 이 프로젝트는 사내 단일 회사용 데모/포트폴리오 범위라 httpOnly 쿠키 + 별도 프록시 구성의 복잡도를 지금 들이지 않기로 결정했다. 실제 운영 전환 시 httpOnly 쿠키로 바꿀 것.

---

## PART A — 백엔드

### Task 1: 인증/테스트 의존성 추가 + pytest 인프라 구성

**Files:**
- Modify: `requirements.txt`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `pytest.ini`

**Interfaces:**
- Produces: `tests/conftest.py`의 `client` fixture (`httpx`/FastAPI `TestClient`, `get_db`가 SQLite 인메모리를 쓰도록 오버라이드됨) — 이후 모든 백엔드 테스트가 이 fixture를 씀

- [ ] **Step 1: requirements.txt에 의존성 추가**

```txt
fastapi==0.121.2
uvicorn==0.38.0
python-dotenv==1.2.1
google-genai==2.16.0
python-multipart==0.0.20
sqlalchemy==2.0.44
psycopg[binary]==3.2.10
bcrypt==5.0.0
pyjwt==2.13.0
pytest==9.1.1
httpx==0.28.1
```

- [ ] **Step 2: 설치**

Run: `./venv/bin/pip install -r requirements.txt`
Expected: 에러 없이 완료

- [ ] **Step 3: pytest.ini 작성**

```ini
[pytest]
testpaths = tests
```

- [ ] **Step 4: tests/__init__.py 생성 (빈 파일)**

- [ ] **Step 5: tests/conftest.py 작성 — SQLite 인메모리로 get_db를 오버라이드하는 TestClient fixture**

```python
import os

os.environ.setdefault("DATABASE_URL", "postgresql://unused:unused@localhost/unused")
os.environ.setdefault("JWT_SECRET", "test-secret-key-not-for-production")
os.environ.setdefault("GOOGLE_API_KEY", "test-key")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from db import Base, get_db
from main import app

TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
)
TestSessionLocal = sessionmaker(bind=TEST_ENGINE, autoflush=False, autocommit=False)


@pytest.fixture()
def client():
    Base.metadata.create_all(bind=TEST_ENGINE)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=TEST_ENGINE)
```

- [ ] **Step 6: 더미 테스트로 fixture 동작 확인**

`tests/test_health.py`:

```python
def test_health_check(client):
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
```

Run: `./venv/bin/pytest tests/test_health.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add requirements.txt pytest.ini tests/__init__.py tests/conftest.py tests/test_health.py
git commit -m "test: pytest + SQLite 테스트 DB 인프라 구성"
```

---

### Task 2: 인증 유틸 (`auth.py`) — 비밀번호 해시, JWT, `get_current_user`

**Files:**
- Create: `auth.py`
- Create: `tests/test_auth_utils.py`
- Modify: `.env.example`
- Modify: `.env`

**Interfaces:**
- Produces:
  - `hash_password(password: str) -> str`
  - `verify_password(password: str, password_hash: str) -> bool`
  - `create_access_token(user_id: int) -> str`
  - `decode_access_token(token: str) -> int` (실패 시 `HTTPException(401, "AUTH_TOKEN_INVALID")`)
  - `get_current_user(authorization: str = Header(...), db: Session = Depends(get_db)) -> User` — FastAPI dependency
- Consumes: `models.User`, `db.get_db`

- [ ] **Step 1: .env.example에 JWT_SECRET 추가**

```txt
GOOGLE_API_KEY=sk-ant-xxxxxxxxxxxx
DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require
JWT_SECRET=change-me-min-32-chars
```

- [ ] **Step 2: 실제 .env에 JWT_SECRET 값 채우기**

Run: `python3 -c "import secrets; print(secrets.token_hex(32))"` 로 값을 생성해 `.env`의 `JWT_SECRET=`에 붙여넣는다. (이 파일은 git에 커밋되지 않는다.)

- [ ] **Step 3: 실패하는 테스트 작성 — `tests/test_auth_utils.py`**

```python
from auth import create_access_token, decode_access_token, hash_password, verify_password


def test_hash_password_and_verify_roundtrip():
    hashed = hash_password("s3cr3t-pass")
    assert hashed != "s3cr3t-pass"
    assert verify_password("s3cr3t-pass", hashed) is True
    assert verify_password("wrong-pass", hashed) is False


def test_create_and_decode_access_token_roundtrip():
    token = create_access_token(user_id=42)
    assert decode_access_token(token) == 42


def test_decode_access_token_rejects_garbage():
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token("not-a-real-token")
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "AUTH_TOKEN_INVALID"
```

- [ ] **Step 4: 테스트 실행 → 실패 확인**

Run: `./venv/bin/pytest tests/test_auth_utils.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'auth'`

- [ ] **Step 5: `auth.py` 구현**

```python
import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from db import get_db
from models import User

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
JWT_EXPIRES_HOURS = 24 * 7


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRES_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="AUTH_TOKEN_EXPIRED")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="AUTH_TOKEN_INVALID")
    return int(payload["sub"])


def get_current_user(
    authorization: str = Header(default=""), db: Session = Depends(get_db)
) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="AUTH_TOKEN_INVALID")
    token = authorization.removeprefix("Bearer ")
    user_id = decode_access_token(token)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="AUTH_TOKEN_INVALID")
    return user
```

- [ ] **Step 6: 테스트 재실행 → 통과 확인**

Run: `./venv/bin/pytest tests/test_auth_utils.py -v`
Expected: PASS (3 passed)

- [ ] **Step 7: Commit**

```bash
git add auth.py tests/test_auth_utils.py .env.example
git commit -m "feat: 비밀번호 해시/JWT 인증 유틸 추가"
```

---

### Task 3: 데이터 모델 — `User`/`Group`/`GroupMembership`/`Announcement` + 기존 테이블 `group_id`

**Files:**
- Modify: `models.py`

**Interfaces:**
- Produces: SQLAlchemy 모델 `User`, `Group`, `GroupMembership`, `Announcement` (Task 4~7이 사용), `Todo.group_id`/`ChatMessage.group_id`(NOT NULL), `Schedule.group_id`/`Document.group_id`(nullable), `Document.is_template`

- [ ] **Step 1: `models.py` 전체를 아래 내용으로 교체**

```python
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    PrimaryKeyConstraint,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from db import Base

DOCUMENT_CATEGORIES = ("기획", "디자인", "개발", "마케팅", "기타", "통화")
DOCUMENT_SOURCE_TYPES = ("call", "document")
USER_ROLES = ("admin", "member")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(f"role IN {USER_ROLES}", name="ck_users_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="member")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class GroupMembership(Base):
    __tablename__ = "group_memberships"
    __table_args__ = (PrimaryKeyConstraint("user_id", "group_id"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Todo(Base):
    __tablename__ = "todos"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id"), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            f"category IN {DOCUMENT_CATEGORIES}", name="ck_documents_category"
        ),
        CheckConstraint(
            f"source_type IN {DOCUMENT_SOURCE_TYPES}", name="ck_documents_source_type"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id"), nullable=True)
    is_template: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), nullable=False)
    sender: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_bot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

- [ ] **Step 2: 모델 임포트가 깨지지 않는지 확인**

Run: `./venv/bin/python -c "import models"`
Expected: 에러 없이 종료

- [ ] **Step 3: Commit**

```bash
git add models.py
git commit -m "feat: User/Group/GroupMembership/Announcement 모델 및 기존 테이블 group_id 추가"
```

---

### Task 4: 회원가입/로그인/`/me` 엔드포인트

**Files:**
- Create: `routers/__init__.py`
- Create: `routers/auth.py`
- Modify: `main.py`
- Create: `tests/test_auth_routes.py`

**Interfaces:**
- Consumes: `auth.hash_password`, `auth.verify_password`, `auth.create_access_token`, `auth.get_current_user`, `models.User`, `models.GroupMembership`, `models.Group`
- Produces: `POST /api/v1/auth/signup`, `POST /api/v1/auth/login`, `GET /api/v1/me` — 이후 프론트 Task 9가 그대로 호출

- [ ] **Step 1: 실패하는 테스트 작성 — `tests/test_auth_routes.py`**

```python
def test_signup_first_user_becomes_admin(client):
    res = client.post(
        "/api/v1/auth/signup",
        json={"email": "admin@onque.dev", "password": "password123", "name": "관리자"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["user"]["role"] == "admin"
    assert body["data"]["token"]


def test_signup_second_user_becomes_member(client):
    client.post(
        "/api/v1/auth/signup",
        json={"email": "admin@onque.dev", "password": "password123", "name": "관리자"},
    )
    res = client.post(
        "/api/v1/auth/signup",
        json={"email": "member@onque.dev", "password": "password123", "name": "직원"},
    )
    assert res.json()["data"]["user"]["role"] == "member"


def test_signup_duplicate_email_returns_409(client):
    payload = {"email": "dup@onque.dev", "password": "password123", "name": "중복"}
    client.post("/api/v1/auth/signup", json=payload)
    res = client.post("/api/v1/auth/signup", json=payload)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "USER_EMAIL_DUPLICATE"


def test_login_success_returns_token(client):
    client.post(
        "/api/v1/auth/signup",
        json={"email": "login@onque.dev", "password": "password123", "name": "로그인"},
    )
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "login@onque.dev", "password": "password123"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["token"]


def test_login_wrong_password_returns_401(client):
    client.post(
        "/api/v1/auth/signup",
        json={"email": "wrong@onque.dev", "password": "password123", "name": "테스트"},
    )
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "wrong@onque.dev", "password": "incorrect"},
    )
    assert res.status_code == 401


def test_me_requires_auth_header(client):
    res = client.get("/api/v1/me")
    assert res.status_code == 401


def test_me_returns_current_user_and_groups(client):
    signup = client.post(
        "/api/v1/auth/signup",
        json={"email": "me@onque.dev", "password": "password123", "name": "나"},
    )
    token = signup.json()["data"]["token"]
    res = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["data"]["user"]["email"] == "me@onque.dev"
    assert res.json()["data"]["groups"] == []
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `./venv/bin/pytest tests/test_auth_routes.py -v`
Expected: FAIL (404, 라우트 없음)

- [ ] **Step 3: `routers/__init__.py` 생성 (빈 파일)**

- [ ] **Step 4: `routers/auth.py` 구현**

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import create_access_token, get_current_user, hash_password, verify_password
from db import get_db
from models import Group, GroupMembership, User

router = APIRouter(prefix="/api/v1", tags=["auth"])


class SignupBody(BaseModel):
    email: str
    password: str
    name: str


class LoginBody(BaseModel):
    email: str
    password: str


def _serialize_user(user: User) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role}


@router.post("/auth/signup")
def signup(body: SignupBody, db: Session = Depends(get_db)):
    existing = db.scalar(select(User).where(User.email == body.email))
    if existing:
        raise HTTPException(
            status_code=409,
            detail={"code": "USER_EMAIL_DUPLICATE", "message": "이미 가입된 이메일입니다."},
        )

    is_first_user = db.scalar(select(User).limit(1)) is None
    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        name=body.name,
        role="admin" if is_first_user else "member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    return {
        "success": True,
        "data": {"user": _serialize_user(user), "token": token},
        "error": None,
    }


@router.post("/auth/login")
def login(body: LoginBody, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_INVALID_CREDENTIALS", "message": "이메일 또는 비밀번호가 올바르지 않습니다."},
        )

    token = create_access_token(user.id)
    return {
        "success": True,
        "data": {"user": _serialize_user(user), "token": token},
        "error": None,
    }


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    memberships = db.scalars(
        select(GroupMembership).where(GroupMembership.user_id == current_user.id)
    ).all()
    group_ids = [m.group_id for m in memberships]
    groups = db.scalars(select(Group).where(Group.id.in_(group_ids))).all() if group_ids else []

    return {
        "success": True,
        "data": {
            "user": _serialize_user(current_user),
            "groups": [{"id": g.id, "name": g.name} for g in groups],
        },
        "error": None,
    }
```

- [ ] **Step 5: `main.py`에 라우터 등록 — 상단 import 블록과 `app = FastAPI()` 직후에 추가**

`main.py`의 `from db import Base, engine, get_db` 다음 줄에 추가:

```python
from routers.auth import router as auth_router
```

`app.add_middleware(...)` 블록 바로 다음에 추가:

```python
app.include_router(auth_router)
```

- [ ] **Step 6: 에러 핸들러가 `{code, message}` detail을 `error` envelope로 감싸도록 `main.py`에 예외 핸들러 추가**

`main.py`의 `app = FastAPI()` 다음, `add_middleware` 앞에 추가:

```python
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException as FastAPIHTTPException


@app.exception_handler(FastAPIHTTPException)
async def http_exception_handler(request, exc: FastAPIHTTPException):
    if isinstance(exc.detail, dict):
        error = exc.detail
    else:
        error = {"code": "INTERNAL_ERROR", "message": str(exc.detail)}
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "data": None, "error": error},
    )
```

- [ ] **Step 7: 테스트 재실행 → 통과 확인**

Run: `./venv/bin/pytest tests/test_auth_routes.py -v`
Expected: PASS (7 passed)

- [ ] **Step 8: 전체 회귀 테스트**

Run: `./venv/bin/pytest -v`
Expected: 지금까지 작성된 모든 테스트 PASS

- [ ] **Step 9: Commit**

```bash
git add routers/ main.py tests/test_auth_routes.py
git commit -m "feat: 회원가입/로그인/me 엔드포인트 추가"
```

---

### Task 5: 그룹 CRUD + 멤버 관리 (admin 전용)

**Files:**
- Create: `routers/groups.py`
- Modify: `main.py`
- Create: `tests/test_group_routes.py`

**Interfaces:**
- Consumes: `auth.get_current_user`, `models.Group`, `models.GroupMembership`, `models.User`
- Produces: `POST /api/v1/groups`, `GET /api/v1/groups`, `POST /api/v1/groups/{id}/members`, `DELETE /api/v1/groups/{id}/members/{userId}` — Task 7(그룹 스코프 적용)과 프론트 Task 11이 사용

- [ ] **Step 1: 테스트 헬퍼 + 실패하는 테스트 작성 — `tests/test_group_routes.py`**

```python
def _signup(client, email, name="테스트"):
    res = client.post(
        "/api/v1/auth/signup", json={"email": email, "password": "password123", "name": name}
    )
    body = res.json()["data"]
    return body["token"], body["user"]["id"]


def test_admin_can_create_group(client):
    admin_token, _ = _signup(client, "admin@onque.dev")
    res = client.post(
        "/api/v1/groups",
        json={"name": "행사기획팀"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["name"] == "행사기획팀"


def test_member_cannot_create_group(client):
    _signup(client, "admin@onque.dev")
    member_token, _ = _signup(client, "member@onque.dev")
    res = client.post(
        "/api/v1/groups",
        json={"name": "행사기획팀"},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "GROUP_CREATE_FORBIDDEN"


def test_admin_can_add_member_to_group(client):
    admin_token, _ = _signup(client, "admin@onque.dev")
    _, member_id = _signup(client, "member@onque.dev")
    group = client.post(
        "/api/v1/groups",
        json={"name": "행사기획팀"},
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()["data"]

    res = client.post(
        f"/api/v1/groups/{group['id']}/members",
        json={"user_id": member_id},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200

    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {admin_token}"})


def test_member_cannot_add_member(client):
    admin_token, _ = _signup(client, "admin@onque.dev")
    _, member_id = _signup(client, "member@onque.dev")
    other_token, other_id = _signup(client, "other@onque.dev")
    group = client.post(
        "/api/v1/groups",
        json={"name": "행사기획팀"},
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()["data"]

    res = client.post(
        f"/api/v1/groups/{group['id']}/members",
        json={"user_id": other_id},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "GROUP_MEMBER_ADD_FORBIDDEN"


def test_get_groups_returns_only_my_groups(client):
    admin_token, admin_id = _signup(client, "admin@onque.dev")
    _, member_id = _signup(client, "member@onque.dev")
    group_a = client.post(
        "/api/v1/groups", json={"name": "A팀"}, headers={"Authorization": f"Bearer {admin_token}"}
    ).json()["data"]
    client.post(
        "/api/v1/groups", json={"name": "B팀"}, headers={"Authorization": f"Bearer {admin_token}"}
    )
    client.post(
        f"/api/v1/groups/{group_a['id']}/members",
        json={"user_id": member_id},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    member_token = client.post(
        "/api/v1/auth/login", json={"email": "member@onque.dev", "password": "password123"}
    ).json()["data"]["token"]
    res = client.get("/api/v1/groups", headers={"Authorization": f"Bearer {member_token}"})
    names = [g["name"] for g in res.json()["data"]]
    assert names == ["A팀"]
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `./venv/bin/pytest tests/test_group_routes.py -v`
Expected: FAIL (404)

- [ ] **Step 3: `routers/groups.py` 구현**

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import get_current_user
from db import get_db
from models import Group, GroupMembership, User

router = APIRouter(prefix="/api/v1", tags=["groups"])


def _require_admin(user: User) -> None:
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": "GROUP_CREATE_FORBIDDEN", "message": "관리자만 가능한 작업입니다."},
        )


class GroupCreateBody(BaseModel):
    name: str


class GroupMemberBody(BaseModel):
    user_id: int


@router.post("/groups")
def create_group(
    body: GroupCreateBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    group = Group(name=body.name, created_by=current_user.id)
    db.add(group)
    db.commit()
    db.refresh(group)
    db.add(GroupMembership(user_id=current_user.id, group_id=group.id))
    db.commit()
    return {"success": True, "data": {"id": group.id, "name": group.name}, "error": None}


@router.get("/groups")
def list_my_groups(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    memberships = db.scalars(
        select(GroupMembership).where(GroupMembership.user_id == current_user.id)
    ).all()
    group_ids = [m.group_id for m in memberships]
    groups = db.scalars(select(Group).where(Group.id.in_(group_ids))).all() if group_ids else []
    return {
        "success": True,
        "data": [{"id": g.id, "name": g.name} for g in groups],
        "error": None,
    }


@router.post("/groups/{group_id}/members")
def add_group_member(
    group_id: int,
    body: GroupMemberBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": "GROUP_MEMBER_ADD_FORBIDDEN", "message": "관리자만 가능한 작업입니다."},
        )
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(
            status_code=404, detail={"code": "GROUP_NOT_FOUND", "message": "그룹을 찾을 수 없습니다."}
        )
    target_user = db.get(User, body.user_id)
    if not target_user:
        raise HTTPException(
            status_code=404, detail={"code": "USER_NOT_FOUND", "message": "사용자를 찾을 수 없습니다."}
        )
    existing = db.get(GroupMembership, {"user_id": body.user_id, "group_id": group_id})
    if not existing:
        db.add(GroupMembership(user_id=body.user_id, group_id=group_id))
        db.commit()
    return {"success": True, "data": {"group_id": group_id, "user_id": body.user_id}, "error": None}


@router.delete("/groups/{group_id}/members/{user_id}")
def remove_group_member(
    group_id: int,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": "GROUP_MEMBER_ADD_FORBIDDEN", "message": "관리자만 가능한 작업입니다."},
        )
    membership = db.get(GroupMembership, {"user_id": user_id, "group_id": group_id})
    if membership:
        db.delete(membership)
        db.commit()
    return {"success": True, "data": {"deleted": True}, "error": None}
```

- [ ] **Step 4: `main.py`에 라우터 등록**

`from routers.auth import router as auth_router` 다음 줄에 추가:

```python
from routers.groups import router as groups_router
```

`app.include_router(auth_router)` 다음 줄에 추가:

```python
app.include_router(groups_router)
```

- [ ] **Step 5: 테스트 재실행 → 통과 확인**

Run: `./venv/bin/pytest tests/test_group_routes.py -v`
Expected: PASS (5 passed)

- [ ] **Step 6: 전체 회귀 테스트**

Run: `./venv/bin/pytest -v`
Expected: 전체 PASS

- [ ] **Step 7: Commit**

```bash
git add routers/groups.py main.py tests/test_group_routes.py
git commit -m "feat: 그룹 생성/조회, 멤버 추가/제거 엔드포인트 추가 (admin 전용)"
```

---

### Task 6: 공지사항 엔드포인트

**Files:**
- Create: `routers/announcements.py`
- Modify: `main.py`
- Create: `tests/test_announcement_routes.py`

**Interfaces:**
- Consumes: `auth.get_current_user`, `models.Announcement`
- Produces: `GET /api/v1/announcements`, `POST /api/v1/announcements`

- [ ] **Step 1: 실패하는 테스트 작성 — `tests/test_announcement_routes.py`**

```python
def _signup(client, email):
    res = client.post(
        "/api/v1/auth/signup", json={"email": email, "password": "password123", "name": "테스트"}
    )
    return res.json()["data"]["token"]


def test_admin_can_post_announcement(client):
    token = _signup(client, "admin@onque.dev")
    res = client.post(
        "/api/v1/announcements",
        json={"title": "전사 공지", "content": "내일 휴무입니다."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["title"] == "전사 공지"


def test_member_cannot_post_announcement(client):
    _signup(client, "admin@onque.dev")
    member_token = _signup(client, "member@onque.dev")
    res = client.post(
        "/api/v1/announcements",
        json={"title": "공지", "content": "내용"},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert res.status_code == 403


def test_anyone_can_list_announcements(client):
    admin_token = _signup(client, "admin@onque.dev")
    client.post(
        "/api/v1/announcements",
        json={"title": "공지1", "content": "내용1"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    member_token = _signup(client, "member@onque.dev")
    res = client.get("/api/v1/announcements", headers={"Authorization": f"Bearer {member_token}"})
    assert len(res.json()["data"]) == 1
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `./venv/bin/pytest tests/test_announcement_routes.py -v`
Expected: FAIL (404)

- [ ] **Step 3: `routers/announcements.py` 구현**

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import get_current_user
from db import get_db
from models import Announcement, User

router = APIRouter(prefix="/api/v1", tags=["announcements"])


class AnnouncementCreateBody(BaseModel):
    title: str
    content: str


def _serialize(a: Announcement) -> dict:
    return {
        "id": a.id,
        "title": a.title,
        "content": a.content,
        "author_id": a.author_id,
        "created_at": a.created_at.isoformat(),
    }


@router.get("/announcements")
def list_announcements(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    items = db.scalars(select(Announcement).order_by(Announcement.created_at.desc())).all()
    return {"success": True, "data": [_serialize(a) for a in items], "error": None}


@router.post("/announcements")
def create_announcement(
    body: AnnouncementCreateBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": "ANNOUNCEMENT_CREATE_FORBIDDEN", "message": "관리자만 공지를 작성할 수 있습니다."},
        )
    announcement = Announcement(title=body.title, content=body.content, author_id=current_user.id)
    db.add(announcement)
    db.commit()
    db.refresh(announcement)
    return {"success": True, "data": _serialize(announcement), "error": None}
```

- [ ] **Step 4: `main.py`에 라우터 등록**

`from routers.groups import router as groups_router` 다음 줄에 추가:

```python
from routers.announcements import router as announcements_router
```

`app.include_router(groups_router)` 다음 줄에 추가:

```python
app.include_router(announcements_router)
```

- [ ] **Step 5: 테스트 재실행 → 통과 확인**

Run: `./venv/bin/pytest tests/test_announcement_routes.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add routers/announcements.py main.py tests/test_announcement_routes.py
git commit -m "feat: 전사 공지사항 조회/작성 엔드포인트 추가"
```

---

### Task 7: 기존 엔드포인트에 그룹 스코프 적용 (todos/schedules/documents/chat)

**Files:**
- Modify: `main.py`
- Create: `tests/test_group_scoping.py`

**Interfaces:**
- Consumes: `auth.get_current_user`, `models.GroupMembership`
- Produces: `_require_group_member(user, group_id, db)` 헬퍼 — 기존 `/todos`, `/schedules`, `/documents`, `/chat/messages` 전부가 `group_id` 쿼리 파라미터 + `Authorization` 헤더를 요구하게 됨. 신규 `POST /schedules` — admin이 `group_id` 없이 호출하면 전사 일정(휴일·회의)을 등록한다 (지금까지는 일정을 만드는 유일한 경로가 채팅 추출뿐이라 전사 일정을 만들 방법이 없었다).

- [ ] **Step 1: 실패하는 테스트 작성 — `tests/test_group_scoping.py`**

```python
def _setup_two_groups(client):
    admin_token = client.post(
        "/api/v1/auth/signup",
        json={"email": "admin@onque.dev", "password": "password123", "name": "관리자"},
    ).json()["data"]["token"]
    group_a = client.post(
        "/api/v1/groups", json={"name": "A팀"}, headers={"Authorization": f"Bearer {admin_token}"}
    ).json()["data"]
    group_b = client.post(
        "/api/v1/groups", json={"name": "B팀"}, headers={"Authorization": f"Bearer {admin_token}"}
    ).json()["data"]
    return admin_token, group_a["id"], group_b["id"]


def test_todos_requires_group_id(client):
    admin_token, group_a, _ = _setup_two_groups(client)
    res = client.get("/todos", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 422


def test_todos_isolated_between_groups(client):
    admin_token, group_a, group_b = _setup_two_groups(client)
    client.post(
        "/chat/messages",
        params={"group_id": group_a},
        json={"sender": "관리자", "content": "할일: A팀 킥오프 준비"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    res_a = client.get(
        "/todos", params={"group_id": group_a}, headers={"Authorization": f"Bearer {admin_token}"}
    )
    res_b = client.get(
        "/todos", params={"group_id": group_b}, headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert len(res_a.json()) >= 0
    assert res_b.json() == []


def test_todos_rejects_non_member(client):
    admin_token, group_a, _ = _setup_two_groups(client)
    other_token = client.post(
        "/api/v1/auth/signup",
        json={"email": "other@onque.dev", "password": "password123", "name": "타인"},
    ).json()["data"]["token"]
    res = client.get(
        "/todos", params={"group_id": group_a}, headers={"Authorization": f"Bearer {other_token}"}
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "GROUP_ACCESS_FORBIDDEN"


def test_chat_messages_isolated_between_groups(client):
    admin_token, group_a, group_b = _setup_two_groups(client)
    client.post(
        "/chat/messages",
        params={"group_id": group_a},
        json={"sender": "관리자", "content": "안녕하세요"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    res_a = client.get(
        "/chat/messages", params={"group_id": group_a}, headers={"Authorization": f"Bearer {admin_token}"}
    )
    res_b = client.get(
        "/chat/messages", params={"group_id": group_b}, headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert len(res_a.json()) == 1
    assert res_b.json() == []


def test_admin_can_create_company_wide_schedule_visible_in_every_group(client):
    admin_token, group_a, group_b = _setup_two_groups(client)
    res = client.post(
        "/schedules",
        json={"title": "창립기념일 휴무", "scheduled_date": "2026-09-01"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    assert res.json()["title"] == "창립기념일 휴무"

    res_a = client.get(
        "/schedules", params={"group_id": group_a}, headers={"Authorization": f"Bearer {admin_token}"}
    )
    res_b = client.get(
        "/schedules", params={"group_id": group_b}, headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert "창립기념일 휴무" in [s["title"] for s in res_a.json()]
    assert "창립기념일 휴무" in [s["title"] for s in res_b.json()]


def test_member_cannot_create_company_wide_schedule(client):
    _setup_two_groups(client)
    member_signup = client.post(
        "/api/v1/auth/signup",
        json={"email": "member@onque.dev", "password": "password123", "name": "직원"},
    ).json()["data"]
    member_token = member_signup["token"]

    res = client.post(
        "/schedules",
        json={"title": "직원이 만든 전사 일정", "scheduled_date": "2026-09-01"},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "SCHEDULE_EDIT_FORBIDDEN"
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `./venv/bin/pytest tests/test_group_scoping.py -v`
Expected: FAIL (기존 엔드포인트가 인증/`group_id` 없이도 200을 반환하므로 `422`/`403` 기대가 어긋남)

- [ ] **Step 3: `main.py` 수정 — import 블록**

`from models import ChatMessage, Document, Schedule, Todo` 줄을 아래로 교체:

```python
from auth import get_current_user
from models import ChatMessage, Document, GroupMembership, Schedule, Todo, User
```

- [ ] **Step 4: `main.py`에 그룹 소속 검증 헬퍼 추가**

`_hint_matches` 함수 바로 다음에 추가:

```python
def _require_group_member(user: User, group_id: int, db: Session) -> None:
    membership = db.get(GroupMembership, {"user_id": user.id, "group_id": group_id})
    if not membership:
        raise HTTPException(
            status_code=403,
            detail={"code": "GROUP_ACCESS_FORBIDDEN", "message": "해당 그룹에 소속되어 있지 않습니다."},
        )
```

- [ ] **Step 5: `/todos` 계열 수정**

```python
@app.get("/todos")
def list_todos(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_group_member(current_user, group_id, db)
    todos = db.scalars(
        select(Todo)
        .where(Todo.group_id == group_id)
        .order_by(Todo.is_done.asc(), Todo.created_at.desc())
    ).all()
    return [_serialize_todo(t) for t in todos]


@app.patch("/todos/{todo_id}")
def update_todo(
    todo_id: int,
    body: TodoUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    todo = db.get(Todo, todo_id)
    if not todo:
        raise HTTPException(status_code=404, detail="할 일을 찾을 수 없습니다.")
    _require_group_member(current_user, todo.group_id, db)
    if body.is_done is not None:
        todo.is_done = body.is_done
    if body.content is not None:
        todo.content = body.content
    if body.due_date is not None:
        todo.due_date = _parse_date(body.due_date)
    db.commit()
    db.refresh(todo)
    return _serialize_todo(todo)


@app.delete("/todos/{todo_id}")
def delete_todo(
    todo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    todo = db.get(Todo, todo_id)
    if not todo:
        raise HTTPException(status_code=404, detail="할 일을 찾을 수 없습니다.")
    _require_group_member(current_user, todo.group_id, db)
    db.delete(todo)
    db.commit()
    return {"deleted": True}
```

- [ ] **Step 6: `/schedules` 계열 수정 (전사 일정 `group_id IS NULL` 포함해서 조회) + 전사 일정 생성 엔드포인트 추가**

```python
class ScheduleCreate(BaseModel):
    title: str
    scheduled_date: str
    group_id: int | None = None


@app.post("/schedules")
def create_schedule(
    body: ScheduleCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.group_id is not None:
        _require_group_member(current_user, body.group_id, db)
    elif current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": "SCHEDULE_EDIT_FORBIDDEN", "message": "전사 일정은 관리자만 등록할 수 있습니다."},
        )
    scheduled = _parse_date(body.scheduled_date)
    if not scheduled:
        raise HTTPException(status_code=400, detail="scheduled_date 형식이 올바르지 않습니다. (YYYY-MM-DD)")
    schedule = Schedule(group_id=body.group_id, title=body.title, scheduled_date=scheduled)
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return _serialize_schedule(schedule)


@app.get("/schedules")
def list_schedules(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_group_member(current_user, group_id, db)
    schedules = db.scalars(
        select(Schedule)
        .where((Schedule.group_id == group_id) | (Schedule.group_id.is_(None)))
        .order_by(Schedule.scheduled_date.asc())
    ).all()
    return [_serialize_schedule(s) for s in schedules]


@app.patch("/schedules/{schedule_id}")
def update_schedule(
    schedule_id: int,
    body: ScheduleUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    schedule = db.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다.")
    if schedule.group_id is not None:
        _require_group_member(current_user, schedule.group_id, db)
    elif current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": "SCHEDULE_EDIT_FORBIDDEN", "message": "전사 일정은 관리자만 수정할 수 있습니다."},
        )
    if body.title is not None:
        schedule.title = body.title
    if body.scheduled_date is not None:
        parsed = _parse_date(body.scheduled_date)
        if parsed:
            schedule.scheduled_date = parsed
    db.commit()
    db.refresh(schedule)
    return _serialize_schedule(schedule)


@app.delete("/schedules/{schedule_id}")
def delete_schedule(
    schedule_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    schedule = db.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다.")
    if schedule.group_id is not None:
        _require_group_member(current_user, schedule.group_id, db)
    elif current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": "SCHEDULE_EDIT_FORBIDDEN", "message": "전사 일정은 관리자만 수정할 수 있습니다."},
        )
    db.delete(schedule)
    db.commit()
    return {"deleted": True}
```

- [ ] **Step 7: `/documents` 계열 수정 (템플릿은 그룹 무관 공유)**

```python
@app.get("/documents")
def list_documents(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_group_member(current_user, group_id, db)
    docs = db.scalars(
        select(Document)
        .where((Document.group_id == group_id) | (Document.is_template.is_(True)))
        .order_by(Document.created_at.desc())
        .limit(100)
    ).all()
    return [_serialize_document(d) for d in docs]


@app.delete("/documents/{document_id}")
def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    if doc.group_id is not None:
        _require_group_member(current_user, doc.group_id, db)
    db.delete(doc)
    db.commit()
    return {"deleted": True}
```

`summarize_call`, `summarize_document`는 그룹에 소속된 사용자가 업로드하는 것이므로 `group_id` 파라미터와 인증을 추가한다:

```python
@app.post("/summarize-call")
async def summarize_call(
    group_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """통화 녹음 파일(mp3, m4a, wav 등)을 받아 Gemini로 요약하고 이력에 저장한다."""
    _require_group_member(current_user, group_id, db)

    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(
            status_code=400,
            detail=f"오디오 파일만 업로드 가능합니다. (현재 content_type: {file.content_type})",
        )

    summary_text = await gemini_service.summarize_upload(file, gemini_service.CALL_SUMMARY_PROMPT)

    doc = Document(
        group_id=group_id,
        source_type="call",
        category="통화",
        filename=file.filename,
        summary=summary_text,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return {
        "id": doc.id,
        "filename": doc.filename,
        "summary": doc.summary,
        "category": doc.category,
    }
```

```python
@app.post("/summarize-document")
async def summarize_document(
    group_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """문서/회의록 파일(pdf, txt, md)을 받아 Gemini로 요약·분류하고 이력에 저장한다."""
    _require_group_member(current_user, group_id, db)

    suffix = os.path.splitext(file.filename or "")[1].lower()
    if suffix not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"pdf, txt, md 파일만 업로드 가능합니다. (현재 확장자: {suffix or '없음'})",
        )

    summary_text = await gemini_service.summarize_upload(
        file, gemini_service.DOCUMENT_SUMMARY_PROMPT
    )
    category = gemini_service.classify_document_category(summary_text)

    doc = Document(
        group_id=group_id,
        source_type="document",
        category=category,
        filename=file.filename,
        summary=summary_text,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return {
        "id": doc.id,
        "filename": doc.filename,
        "summary": doc.summary,
        "category": doc.category,
    }
```

- [ ] **Step 8: `/chat/messages` 계열 수정**

```python
@app.get("/chat/messages")
def list_chat_messages(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_group_member(current_user, group_id, db)
    messages = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.group_id == group_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(50)
    ).all()
    return [_serialize_message(m) for m in reversed(messages)]
```

`_apply_extracted_actions`는 그룹 스코프 안에서 할일/일정을 조작하도록 `group_id`를 받게 바꾼다:

```python
def _apply_extracted_actions(db: Session, group_id: int, actions: dict) -> None:
    for item in actions.get("add_todos", []):
        content = (item.get("content") or "").strip()
        if not content:
            continue
        db.add(
            Todo(
                group_id=group_id,
                content=content,
                due_date=_parse_date(item.get("due_date", "")),
            )
        )

    if actions.get("complete_todo_hints") or actions.get("delete_todo_hints"):
        open_todos = db.scalars(
            select(Todo).where(Todo.group_id == group_id, Todo.is_done.is_(False))
        ).all()
        for hint in actions.get("complete_todo_hints", []):
            for todo in open_todos:
                if not todo.is_done and _hint_matches(todo.content, hint):
                    todo.is_done = True
                    break

        all_todos = db.scalars(select(Todo).where(Todo.group_id == group_id)).all()
        for hint in actions.get("delete_todo_hints", []):
            for todo in all_todos:
                if _hint_matches(todo.content, hint):
                    db.delete(todo)
                    break

    for item in actions.get("add_schedules", []):
        title = (item.get("title") or "").strip()
        scheduled = _parse_date(item.get("date", ""))
        if not title or not scheduled:
            continue
        db.add(Schedule(group_id=group_id, title=title, scheduled_date=scheduled))

    if actions.get("delete_schedule_hints"):
        all_schedules = db.scalars(select(Schedule).where(Schedule.group_id == group_id)).all()
        for hint in actions.get("delete_schedule_hints", []):
            for schedule in all_schedules:
                if _hint_matches(schedule.title, hint):
                    db.delete(schedule)
                    break
```

`create_chat_message`:

```python
@app.post("/chat/messages")
def create_chat_message(
    group_id: int,
    body: ChatMessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_group_member(current_user, group_id, db)
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="메시지 내용이 비어 있습니다.")

    user_message = ChatMessage(group_id=group_id, sender=body.sender, content=content, is_bot=False)
    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    actions = gemini_service.extract_chat_actions(content)
    _apply_extracted_actions(db, group_id, actions)
    db.commit()

    bot_message = None
    if "@비서" in content:
        recent = db.scalars(
            select(ChatMessage)
            .where(ChatMessage.group_id == group_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(10)
        ).all()
        history = [
            {"sender": m.sender, "content": m.content} for m in reversed(recent)
        ]
        reply_text = gemini_service.generate_bot_reply(history, content)
        bot_message = ChatMessage(group_id=group_id, sender="비서", content=reply_text, is_bot=True)
        db.add(bot_message)
        db.commit()
        db.refresh(bot_message)

    todos = db.scalars(
        select(Todo)
        .where(Todo.group_id == group_id)
        .order_by(Todo.is_done.asc(), Todo.created_at.desc())
    ).all()
    schedules = db.scalars(
        select(Schedule)
        .where((Schedule.group_id == group_id) | (Schedule.group_id.is_(None)))
        .order_by(Schedule.scheduled_date.asc())
    ).all()

    return {
        "message": _serialize_message(user_message),
        "bot_message": _serialize_message(bot_message) if bot_message else None,
        "todos": [_serialize_todo(t) for t in todos],
        "schedules": [_serialize_schedule(s) for s in schedules],
    }
```

- [ ] **Step 9: 테스트 재실행 → 통과 확인**

Run: `./venv/bin/pytest tests/test_group_scoping.py -v`
Expected: PASS (6 passed)

- [ ] **Step 10: 전체 회귀 테스트**

Run: `./venv/bin/pytest -v`
Expected: 지금까지 작성된 전체 테스트 PASS

- [ ] **Step 11: Commit**

```bash
git add main.py tests/test_group_scoping.py
git commit -m "feat: todos/schedules/documents/chat 엔드포인트에 그룹 스코프 적용"
```

---

### Task 8: 기존 데이터 마이그레이션 스크립트

**Files:**
- Create: `scripts/migrate_add_groups.py`

**Interfaces:**
- Consumes: `db.Base`, `db.engine`, `db.SessionLocal`, `models.Group`, `models.User`
- Produces: 실행형 스크립트 — Task 3의 스키마 변경분을 실제(Neon) DB에 반영하고 기존 `todos`/`chat_messages` 레코드를 "기본 그룹"으로 이관

- [ ] **Step 1: `scripts/migrate_add_groups.py` 작성**

```python
"""그룹 구조 도입 마이그레이션.

실행 순서:
1. 서버를 한 번 기동해 users/groups/group_memberships/announcements 테이블을 만든다
   (main.py의 Base.metadata.create_all이 신규 테이블만 생성한다).
2. POST /api/v1/auth/signup 으로 최초 관리자 계정을 만든다.
3. 이 스크립트를 실행한다 — 기존 todos/chat_messages/schedules/documents 테이블에
   group_id 컬럼을 추가하고, 이미 있던 todos/chat_messages 레코드를 "기본 그룹"으로 이관한다.
"""

from sqlalchemy import select, text

from db import SessionLocal, engine
from models import Group, User


def _column_exists(conn, table: str, column: str) -> bool:
    result = conn.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = :column"
        ),
        {"table": table, "column": column},
    )
    return result.first() is not None


def _add_missing_columns() -> None:
    with engine.begin() as conn:
        if not _column_exists(conn, "todos", "group_id"):
            conn.execute(text("ALTER TABLE todos ADD COLUMN group_id INTEGER"))
        if not _column_exists(conn, "chat_messages", "group_id"):
            conn.execute(text("ALTER TABLE chat_messages ADD COLUMN group_id INTEGER"))
        if not _column_exists(conn, "schedules", "group_id"):
            conn.execute(text("ALTER TABLE schedules ADD COLUMN group_id INTEGER"))
        if not _column_exists(conn, "documents", "group_id"):
            conn.execute(text("ALTER TABLE documents ADD COLUMN group_id INTEGER"))
        if not _column_exists(conn, "documents", "is_template"):
            conn.execute(
                text(
                    "ALTER TABLE documents ADD COLUMN is_template BOOLEAN NOT NULL DEFAULT false"
                )
            )


def _backfill_default_group() -> int | None:
    db = SessionLocal()
    try:
        admin = db.scalar(select(User).where(User.role == "admin"))
        if admin is None:
            print(
                "admin 계정이 아직 없습니다. "
                "POST /api/v1/auth/signup 으로 첫 계정을 만든 뒤 이 스크립트를 다시 실행하세요."
            )
            return None

        default_group = db.scalar(select(Group).where(Group.name == "기본 그룹"))
        if default_group is None:
            default_group = Group(name="기본 그룹", created_by=admin.id)
            db.add(default_group)
            db.commit()
            db.refresh(default_group)

        db.execute(
            text("UPDATE todos SET group_id = :gid WHERE group_id IS NULL"),
            {"gid": default_group.id},
        )
        db.execute(
            text("UPDATE chat_messages SET group_id = :gid WHERE group_id IS NULL"),
            {"gid": default_group.id},
        )
        db.commit()
        return default_group.id
    finally:
        db.close()


def _enforce_not_null() -> None:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE todos ALTER COLUMN group_id SET NOT NULL"))
        conn.execute(text("ALTER TABLE chat_messages ALTER COLUMN group_id SET NOT NULL"))


def main() -> None:
    _add_missing_columns()
    default_group_id = _backfill_default_group()
    if default_group_id is None:
        return
    _enforce_not_null()
    print(f"마이그레이션 완료. 기본 그룹 id={default_group_id}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 실제 Neon DB에 대해 실행 (서버가 최소 한 번 기동되어 신규 테이블이 생성된 뒤)**

Run: `./venv/bin/python scripts/migrate_add_groups.py`
Expected: admin 계정이 없으면 안내 메시지 후 종료(정상). 있으면 `마이그레이션 완료. 기본 그룹 id=...` 출력

- [ ] **Step 3: Commit**

```bash
git add scripts/migrate_add_groups.py
git commit -m "chore: 그룹 도입에 따른 기존 데이터 마이그레이션 스크립트 추가"
```

---

## PART B — 프론트엔드

### Task 9: 인증 API 클라이언트 + `AuthContext` + 로그인/회원가입 페이지

**Files:**
- Modify: `onque-frontend/lib/api.ts`
- Create: `onque-frontend/lib/auth-storage.ts`
- Create: `onque-frontend/components/AuthContext.tsx`
- Create: `onque-frontend/app/login/page.tsx`
- Create: `onque-frontend/app/signup/page.tsx`
- Modify: `onque-frontend/app/layout.tsx`

**Interfaces:**
- Produces:
  - `lib/auth-storage.ts`: `getToken(): string | null`, `setToken(token: string): void`, `clearToken(): void`
  - `AuthContext`: `useAuth()` → `{ user: MeUser | null, groups: GroupSummary[], loading: boolean, login(email, password): Promise<void>, signup(email, password, name): Promise<void>, logout(): void, refreshMe(): Promise<void> }`
- Consumes: 없음 (최상위 컨텍스트)

- [ ] **Step 1: `lib/auth-storage.ts` 작성 — localStorage 접근을 한 곳에 모은다**

```typescript
const TOKEN_KEY = 'onque_token';

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}
```

- [ ] **Step 2: `lib/api.ts`에 인증 타입/함수 추가 — 기존 `request` 헬퍼를 Authorization 헤더 자동 첨부로 교체**

`API_BASE_URL` 선언 다음에 타입 추가:

```typescript
export type AuthUser = {
  id: number;
  email: string;
  name: string;
  role: 'admin' | 'member';
};

export type GroupSummary = {
  id: number;
  name: string;
};

export type MeResponse = {
  user: AuthUser;
  groups: GroupSummary[];
};

type Envelope<T> = { success: boolean; data: T; error: { code: string; message: string } | null };
```

기존 `request` 함수를 아래로 교체 (Authorization 헤더 자동 첨부 + envelope 언랩):

```typescript
import { getToken } from './auth-storage';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (options?.body) headers['Content-Type'] = 'application/json';
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const message = body?.error?.message || body?.detail || '요청이 실패했습니다.';
    throw new Error(message);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

async function requestEnveloped<T>(path: string, options?: RequestInit): Promise<T> {
  const envelope = await request<Envelope<T>>(path, options);
  return envelope.data;
}
```

파일 맨 아래에 인증 API 함수 추가:

```typescript
export function signup(email: string, password: string, name: string): Promise<{ user: AuthUser; token: string }> {
  return requestEnveloped('/api/v1/auth/signup', {
    method: 'POST',
    body: JSON.stringify({ email, password, name }),
  });
}

export function login(email: string, password: string): Promise<{ user: AuthUser; token: string }> {
  return requestEnveloped('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
}

export function getMe(): Promise<MeResponse> {
  return requestEnveloped('/api/v1/me');
}
```

- [ ] **Step 3: `postFile`도 Authorization 헤더를 붙이도록 수정**

`postFile` 함수를 아래로 교체:

```typescript
async function postFile(path: string, file: File): Promise<SummaryResponse> {
  const formData = new FormData();
  formData.append('file', file);
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    body: formData,
    headers,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || '요약 요청이 실패했습니다.');
  }

  return res.json();
}
```

- [ ] **Step 4: `AuthContext` 작성 — `components/AuthContext.tsx`**

```tsx
'use client';

import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  getMe,
  login as apiLogin,
  signup as apiSignup,
  type AuthUser,
  type GroupSummary,
} from '@/lib/api';
import { clearToken, getToken, setToken } from '@/lib/auth-storage';

type AuthContextValue = {
  user: AuthUser | null;
  groups: GroupSummary[];
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, name: string) => Promise<void>;
  logout: () => void;
  refreshMe: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [groups, setGroups] = useState<GroupSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  const refreshMe = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setGroups([]);
      setLoading(false);
      return;
    }
    try {
      const me = await getMe();
      setUser(me.user);
      setGroups(me.groups);
    } catch {
      clearToken();
      setUser(null);
      setGroups([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshMe();
  }, [refreshMe]);

  const login = useCallback(
    async (email: string, password: string) => {
      const result = await apiLogin(email, password);
      setToken(result.token);
      await refreshMe();
      router.push('/');
    },
    [refreshMe, router]
  );

  const signup = useCallback(
    async (email: string, password: string, name: string) => {
      const result = await apiSignup(email, password, name);
      setToken(result.token);
      await refreshMe();
      router.push('/');
    },
    [refreshMe, router]
  );

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
    setGroups([]);
    router.push('/login');
  }, [router]);

  return (
    <AuthContext.Provider value={{ user, groups, loading, login, signup, logout, refreshMe }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth는 AuthProvider 내부에서만 사용할 수 있습니다.');
  return ctx;
}
```

- [ ] **Step 5: 로그인 페이지 — `app/login/page.tsx`**

```tsx
'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/components/AuthContext';

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : '로그인에 실패했습니다.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-6">
      <h1 className="text-xl font-bold text-foreground">
        On<span className="text-brand">Que</span> 로그인
      </h1>
      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        <input
          type="email"
          required
          placeholder="이메일"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded-lg border border-border px-3 py-2 text-sm"
        />
        <input
          type="password"
          required
          placeholder="비밀번호"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded-lg border border-border px-3 py-2 text-sm"
        />
        {error && <p className="text-xs text-red-500">{error}</p>}
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-brand py-2 text-sm font-semibold text-brand-foreground disabled:opacity-50"
        >
          {submitting ? '로그인 중...' : '로그인'}
        </button>
      </form>
      <p className="mt-4 text-center text-xs text-foreground/60">
        계정이 없으신가요? <Link href="/signup" className="text-brand">회원가입</Link>
      </p>
    </div>
  );
}
```

- [ ] **Step 6: 회원가입 페이지 — `app/signup/page.tsx`**

```tsx
'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/components/AuthContext';

export default function SignupPage() {
  const { signup } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await signup(email, password, name);
    } catch (err) {
      setError(err instanceof Error ? err.message : '회원가입에 실패했습니다.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-6">
      <h1 className="text-xl font-bold text-foreground">
        On<span className="text-brand">Que</span> 회원가입
      </h1>
      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        <input
          type="text"
          required
          placeholder="이름"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full rounded-lg border border-border px-3 py-2 text-sm"
        />
        <input
          type="email"
          required
          placeholder="이메일"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded-lg border border-border px-3 py-2 text-sm"
        />
        <input
          type="password"
          required
          minLength={8}
          placeholder="비밀번호 (8자 이상)"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded-lg border border-border px-3 py-2 text-sm"
        />
        {error && <p className="text-xs text-red-500">{error}</p>}
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-brand py-2 text-sm font-semibold text-brand-foreground disabled:opacity-50"
        >
          {submitting ? '가입 중...' : '가입하기'}
        </button>
      </form>
      <p className="mt-4 text-center text-xs text-foreground/60">
        이미 계정이 있으신가요? <Link href="/login" className="text-brand">로그인</Link>
      </p>
    </div>
  );
}
```

- [ ] **Step 7: `app/layout.tsx`에 `AuthProvider` 추가 — `WorkspaceProvider` 바깥을 감싼다**

`import { WorkspaceProvider } from "@/components/WorkspaceContext";` 다음 줄에 추가:

```tsx
import { AuthProvider } from "@/components/AuthContext";
```

`<WorkspaceProvider>` 여는 태그를 아래로 교체:

```tsx
<AuthProvider>
  <WorkspaceProvider>
```

`</WorkspaceProvider>` 닫는 태그를 아래로 교체:

```tsx
  </WorkspaceProvider>
</AuthProvider>
```

- [ ] **Step 8: 수동 확인 — 개발 서버로 회원가입/로그인 플로우 확인**

Run: `cd onque-frontend && NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001 npm run dev -- -p 3001`
브라우저에서 `http://localhost:3001/signup` → 가입 → `/`로 리다이렉트되고 `localStorage`에 `onque_token`이 저장되는지 확인 (개발자 도구 Application 탭)

- [ ] **Step 9: Commit**

```bash
git add onque-frontend/lib/api.ts onque-frontend/lib/auth-storage.ts onque-frontend/components/AuthContext.tsx onque-frontend/app/login onque-frontend/app/signup onque-frontend/app/layout.tsx
git commit -m "feat: 이메일/비밀번호 로그인·회원가입 및 AuthContext 추가"
```

---

### Task 10: 라우트 보호 — 미인증 접근 시 로그인 페이지로 리다이렉트

**Files:**
- Create: `onque-frontend/components/AuthGuard.tsx`
- Modify: `onque-frontend/app/layout.tsx`

**Interfaces:**
- Consumes: `useAuth()` (Task 9)
- Produces: `<AuthGuard>` — `/login`, `/signup` 이외의 모든 페이지를 감싸 미인증 시 리다이렉트

- [ ] **Step 1: `components/AuthGuard.tsx` 작성**

```tsx
'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { useAuth } from '@/components/AuthContext';

const PUBLIC_PATHS = ['/login', '/signup'];

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const isPublicPath = PUBLIC_PATHS.includes(pathname);

  useEffect(() => {
    if (loading) return;
    if (!user && !isPublicPath) router.push('/login');
    if (user && isPublicPath) router.push('/');
  }, [loading, user, isPublicPath, router]);

  if (loading) return null;
  if (!user && !isPublicPath) return null;
  if (user && isPublicPath) return null;

  return <>{children}</>;
}
```

- [ ] **Step 2: `app/layout.tsx`에서 `<WorkspaceProvider>` 내부를 `<AuthGuard>`로 감싼다**

`import { AuthProvider } from "@/components/AuthContext";` 다음 줄에 추가:

```tsx
import { AuthGuard } from "@/components/AuthGuard";
```

레이아웃의 `<div className="flex min-h-screen">...</div>` 블록 전체를 `<AuthGuard>`로 감싼다:

```tsx
<AuthProvider>
  <WorkspaceProvider>
    <AuthGuard>
      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex min-h-screen min-w-0 flex-1 flex-col">
          <MobileNav />
          <main className="flex-1 overflow-y-auto">{children}</main>
        </div>
      </div>
    </AuthGuard>
  </WorkspaceProvider>
</AuthProvider>
```

- [ ] **Step 3: 수동 확인**

브라우저 시크릿창(로그인 상태 없음)으로 `http://localhost:3001/` 접속 → `/login`으로 리다이렉트되는지 확인. 로그인 후 `/login` 재방문 시 `/`로 리다이렉트되는지 확인.

- [ ] **Step 4: Commit**

```bash
git add onque-frontend/components/AuthGuard.tsx onque-frontend/app/layout.tsx
git commit -m "feat: 미인증 접근 시 로그인 페이지로 리다이렉트하는 라우트 가드 추가"
```

---

### Task 11: `WorkspaceContext`에 그룹 상태 추가 + 사이드바 그룹 전환 UI

**Files:**
- Modify: `onque-frontend/components/WorkspaceContext.tsx`
- Modify: `onque-frontend/components/Sidebar.tsx`
- Modify: `onque-frontend/lib/api.ts`

**Interfaces:**
- Produces: `useWorkspace()`에 `currentGroupId: number | null`, `setCurrentGroupId(id: number): void` 추가 — Task 12에서 모든 API 호출이 이 값을 씀
- Consumes: `useAuth()`의 `groups` (Task 9)

- [ ] **Step 1: `lib/api.ts`의 `getTodos`/`getSchedules`/`getDocuments`/`getChatMessages`/`sendChatMessage`가 `group_id`를 받도록 시그니처 변경**

```typescript
export function getTodos(groupId: number): Promise<Todo[]> {
  return request(`/todos?group_id=${groupId}`);
}

export function updateTodo(id: number, body: { is_done?: boolean }): Promise<Todo> {
  return request(`/todos/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
}

export function deleteTodo(id: number): Promise<void> {
  return request(`/todos/${id}`, { method: 'DELETE' });
}

export function getSchedules(groupId: number): Promise<ScheduleItem[]> {
  return request(`/schedules?group_id=${groupId}`);
}

export function deleteSchedule(id: number): Promise<void> {
  return request(`/schedules/${id}`, { method: 'DELETE' });
}

export function getDocuments(groupId: number): Promise<DocumentRecord[]> {
  return request(`/documents?group_id=${groupId}`);
}

export function deleteDocument(id: number): Promise<void> {
  return request(`/documents/${id}`, { method: 'DELETE' });
}

export function getChatMessages(groupId: number): Promise<ChatMessageRecord[]> {
  return request(`/chat/messages?group_id=${groupId}`);
}

export function sendChatMessage(groupId: number, sender: string, content: string): Promise<ChatSendResult> {
  return request(`/chat/messages?group_id=${groupId}`, {
    method: 'POST',
    body: JSON.stringify({ sender, content }),
  });
}
```

`summarizeCall`/`summarizeDocument`도 `group_id`를 쿼리로 붙이도록 `postFile` 호출부를 수정:

```typescript
export function summarizeCall(groupId: number, file: File): Promise<SummaryResponse> {
  return postFile(`/summarize-call?group_id=${groupId}`, file);
}

export function summarizeDocument(groupId: number, file: File): Promise<SummaryResponse> {
  return postFile(`/summarize-document?group_id=${groupId}`, file);
}
```

- [ ] **Step 2: `components/WorkspaceContext.tsx` 전체를 아래로 교체 — 그룹 상태 + 그룹 없으면 빈 배열로 안전하게 처리**

```tsx
'use client';

import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import {
  deleteSchedule as apiDeleteSchedule,
  deleteTodo as apiDeleteTodo,
  updateTodo as apiUpdateTodo,
  getSchedules,
  getTodos,
  type ScheduleItem,
  type Todo,
} from '@/lib/api';
import { useAuth } from '@/components/AuthContext';

const CURRENT_GROUP_KEY = 'onque_current_group_id';

type WorkspaceContextValue = {
  todos: Todo[];
  schedules: ScheduleItem[];
  loading: boolean;
  currentGroupId: number | null;
  setCurrentGroupId: (id: number) => void;
  refresh: () => Promise<void>;
  applySnapshot: (todos: Todo[], schedules: ScheduleItem[]) => void;
  toggleTodo: (id: number, isDone: boolean) => Promise<void>;
  removeTodo: (id: number) => Promise<void>;
  removeSchedule: (id: number) => Promise<void>;
};

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const { groups } = useAuth();
  const [todos, setTodos] = useState<Todo[]>([]);
  const [schedules, setSchedules] = useState<ScheduleItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentGroupId, setCurrentGroupIdState] = useState<number | null>(null);

  useEffect(() => {
    if (groups.length === 0) {
      setCurrentGroupIdState(null);
      return;
    }
    const saved = typeof window !== 'undefined' ? window.localStorage.getItem(CURRENT_GROUP_KEY) : null;
    const savedId = saved ? Number(saved) : null;
    const stillMember = savedId !== null && groups.some((g) => g.id === savedId);
    setCurrentGroupIdState(stillMember ? savedId : groups[0].id);
  }, [groups]);

  const setCurrentGroupId = useCallback((id: number) => {
    window.localStorage.setItem(CURRENT_GROUP_KEY, String(id));
    setCurrentGroupIdState(id);
  }, []);

  const refresh = useCallback(async () => {
    if (currentGroupId === null) {
      setTodos([]);
      setSchedules([]);
      setLoading(false);
      return;
    }
    try {
      const [nextTodos, nextSchedules] = await Promise.all([
        getTodos(currentGroupId),
        getSchedules(currentGroupId),
      ]);
      setTodos(nextTodos);
      setSchedules(nextSchedules);
    } catch {
      // 대시보드 패널은 조용히 실패한다 — 원인 파악은 채팅/업로드 화면의 에러 메시지에서 이뤄진다.
    } finally {
      setLoading(false);
    }
  }, [currentGroupId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const applySnapshot = useCallback((nextTodos: Todo[], nextSchedules: ScheduleItem[]) => {
    setTodos(nextTodos);
    setSchedules(nextSchedules);
  }, []);

  const toggleTodo = useCallback(async (id: number, isDone: boolean) => {
    const updated = await apiUpdateTodo(id, { is_done: isDone });
    setTodos((prev) => prev.map((t) => (t.id === id ? updated : t)));
  }, []);

  const removeTodo = useCallback(async (id: number) => {
    await apiDeleteTodo(id);
    setTodos((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const removeSchedule = useCallback(async (id: number) => {
    await apiDeleteSchedule(id);
    setSchedules((prev) => prev.filter((s) => s.id !== id));
  }, []);

  return (
    <WorkspaceContext.Provider
      value={{
        todos,
        schedules,
        loading,
        currentGroupId,
        setCurrentGroupId,
        refresh,
        applySnapshot,
        toggleTodo,
        removeTodo,
        removeSchedule,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error('useWorkspace는 WorkspaceProvider 내부에서만 사용할 수 있습니다.');
  return ctx;
}
```

- [ ] **Step 3: `components/Sidebar.tsx`에 그룹 전환 드롭다운 추가**

`import { useWorkspace } from '@/components/WorkspaceContext';` 다음 줄에 추가:

```tsx
import { useAuth } from '@/components/AuthContext';
```

`export function Sidebar() {` 내부, `const { todos } = useWorkspace();` 다음 줄에 추가:

```tsx
const { currentGroupId, setCurrentGroupId } = useWorkspace();
const { groups, user, logout } = useAuth();
```

`<div className="px-6 py-7 border-b border-white/10">...</div>` 블록 바로 다음에 그룹 전환 드롭다운을 추가:

```tsx
<div className="px-4 py-3 border-b border-white/10">
  {groups.length > 0 ? (
    <select
      value={currentGroupId ?? ''}
      onChange={(e) => setCurrentGroupId(Number(e.target.value))}
      className="w-full rounded-md bg-white/10 px-2 py-1.5 text-sm text-white"
    >
      {groups.map((g) => (
        <option key={g.id} value={g.id} className="text-black">
          {g.name}
        </option>
      ))}
    </select>
  ) : (
    <p className="text-xs text-white/50">아직 소속된 그룹이 없습니다. 관리자의 초대를 기다려주세요.</p>
  )}
</div>
```

사이드바 하단 `<div className="px-6 py-5 border-t border-white/10">...</div>` 블록을 아래로 교체 (로그아웃 버튼 추가):

```tsx
<div className="px-6 py-5 border-t border-white/10">
  <p className="text-[11px] font-mono text-sidebar-foreground/40">{user?.name} · {user?.role}</p>
  <button
    type="button"
    onClick={logout}
    className="mt-2 text-[11px] font-mono text-sidebar-foreground/60 hover:text-white"
  >
    로그아웃
  </button>
</div>
```

- [ ] **Step 4: 수동 확인 — 관리자로 그룹 2개 만들고 사이드바에서 전환되는지 확인**

수동으로 `curl`을 이용해 admin 로그인 토큰으로 그룹 2개를 만든 뒤, 브라우저에서 로그인해 사이드바 드롭다운으로 그룹이 전환되는지, `localStorage`의 `onque_current_group_id`가 갱신되는지 확인

- [ ] **Step 5: Commit**

```bash
git add onque-frontend/lib/api.ts onque-frontend/components/WorkspaceContext.tsx onque-frontend/components/Sidebar.tsx
git commit -m "feat: 그룹 상태를 WorkspaceContext에 추가하고 사이드바에 그룹 전환 UI 추가"
```

---

### Task 12: 기존 페이지(calls/chat/history/documents)를 현재 그룹 기준으로 연결

**Files:**
- Modify: `onque-frontend/app/chat/page.tsx`
- Modify: `onque-frontend/app/calls/page.tsx`
- Modify: `onque-frontend/app/documents/page.tsx`
- Modify: `onque-frontend/app/history/page.tsx`

**Interfaces:**
- Consumes: `useWorkspace().currentGroupId` (Task 11), `lib/api.ts`의 `group_id` 파라미터를 받는 함수들 (Task 11)

> 이 네 파일은 각각 기존에 `getChatMessages()`, `sendChatMessage(sender, content)`, `summarizeCall(file)`, `summarizeDocument(file)`, `getDocuments()`를 그룹 인자 없이 호출하고 있었다. 각 파일에서 `useWorkspace()`로 `currentGroupId`를 꺼내 모든 호출부에 첫 인자로 전달하도록 바꾼다. `currentGroupId`가 `null`이면("아직 그룹 없음") 데이터 요청 대신 안내 문구를 보여준다.

- [ ] **Step 1: 각 파일에서 API 호출부를 그룹 인자 포함 형태로 바꾼다**

먼저 각 파일을 읽고 정확한 호출 위치를 확인한 뒤 다음 패턴으로 고친다 (파일마다 실제 코드에 맞게 적용):

```tsx
const { currentGroupId } = useWorkspace();

useEffect(() => {
  if (currentGroupId === null) return;
  getChatMessages(currentGroupId).then(setMessages);
}, [currentGroupId]);
```

`chat/page.tsx`의 메시지 전송부:
```tsx
if (currentGroupId === null) return;
const result = await sendChatMessage(currentGroupId, sender, content);
```

`calls/page.tsx`의 업로드부:
```tsx
if (currentGroupId === null) return;
const result = await summarizeCall(currentGroupId, file);
```

`documents/page.tsx`의 업로드부:
```tsx
if (currentGroupId === null) return;
const result = await summarizeDocument(currentGroupId, file);
```

`documents/page.tsx`(또는 `history/page.tsx`, 실제로 `getDocuments`를 호출하는 파일)의 목록 조회부:
```tsx
useEffect(() => {
  if (currentGroupId === null) return;
  getDocuments(currentGroupId).then(setDocuments);
}, [currentGroupId]);
```

각 파일 상단에 `currentGroupId === null`일 때 렌더링할 안내 블록을 추가:
```tsx
if (currentGroupId === null) {
  return (
    <div className="mx-auto max-w-2xl px-6 py-10 text-sm text-foreground/60">
      아직 소속된 그룹이 없습니다. 관리자가 그룹에 초대하면 이용할 수 있습니다.
    </div>
  );
}
```

- [ ] **Step 2: 수동 확인 — 그룹 A/B를 오가며 각 페이지의 데이터가 바뀌는지 확인**

브라우저에서 사이드바 드롭다운으로 그룹을 전환하며 `/chat`, `/calls`, `/documents`, `/history` 각 페이지가 그룹별로 다른 데이터를 보여주는지 확인

- [ ] **Step 3: Commit**

```bash
git add onque-frontend/app/chat onque-frontend/app/calls onque-frontend/app/documents onque-frontend/app/history
git commit -m "feat: calls/chat/history/documents 페이지가 현재 선택된 그룹 기준으로 동작하도록 연결"
```

---

## 완료 후 수동 시연 체크리스트

1. 백엔드(`uvicorn main:app`) + 프론트(`npm run dev`) 기동
2. `/signup`에서 첫 계정 생성 → 자동으로 admin
3. `scripts/migrate_add_groups.py` 실행 (기존 데모 데이터를 "기본 그룹"으로 이관)
4. admin으로 그룹 2개 생성, 두 번째 테스트 계정을 그 중 하나에 초대
5. 두 계정으로 각각 로그인해 채팅/할일/일정/문서가 그룹별로 분리되어 보이는지 확인
6. 관리자 계정으로 공지사항 작성 → 다른 계정에서도 보이는지 확인
