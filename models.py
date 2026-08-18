from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from db import Base

DOCUMENT_CATEGORIES = ("기획", "디자인", "개발", "마케팅", "기타", "통화")
DOCUMENT_SOURCE_TYPES = ("call", "document")
USER_ROLES = ("admin", "member")
GROUP_ROLES = ("admin", "member")
COMMITMENT_STATUSES = ("proposed", "confirmed", "fulfilled", "dismissed")
COMMITMENT_SOURCE_TYPES = ("call", "document", "chat")
# 그룹을 만들면 빈 채팅 목록 대신 바로 쓸 수 있는 방 하나를 함께 만든다.
DEFAULT_CHAT_ROOM_NAME = "일반"


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
    # 요청 편승 스윕의 쿨다운 기준. null이면 한 번도 안 돌았음 — 백필 불필요.
    last_swept_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 직전 스윕이 "무엇을 얼마나 했는지". last_swept_at은 언제 돌았는지만 알려주고
    # 성과는 어디에도 안 남아서, 화면에 "대화 34개에서 2건 찾음"을 띄울 수 없었다.
    #
    # 훑을 게 없었던 스윕은 이 값을 건드리지 않는다. 0으로 덮으면 "방금 아무것도
    # 못 찾음"과 "10분간 새 대화가 없음"이 화면에서 같아 보인다.
    #
    # 시각을 따로 두는 이유: last_swept_at은 쿨다운 표식이라 훑을 게 없어도
    # 갱신된다. 그 값과 아래 개수를 나란히 쓰면 "방금 · 대화 34개에서 2건"처럼
    # 서로 다른 순간의 사실이 한 사건으로 읽힌다. 개수와 짝이 맞는 시각이 필요하다.
    last_scan_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sweep_scanned: Mapped[int | None] = mapped_column(nullable=True)
    last_sweep_found: Mapped[int | None] = mapped_column(nullable=True)


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


class GroupInvitation(Base):
    """가입 전인 사람도 미리 초대해 두기 위한 대기 초대.

    가입만으로는 그룹에 합류하지 않는다. 초대받은 사람이 직접 수락해야
    합류한다. 이게 없으면 상대가 먼저 가입할 때까지 초대를 보낼 방법이 없다.
    """

    __tablename__ = "group_invitations"
    __table_args__ = (
        UniqueConstraint("group_id", "email", name="uq_group_invitations_group_email"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), nullable=False)
    # 항상 소문자로 저장한다. 대소문자만 다른 초대가 둘로 갈라지면 아무도 못 찾는다.
    email: Mapped[str] = mapped_column(Text, nullable=False)
    invited_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # 수락하면 시각이 찍힌다. None이면 아직 대기 중.
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), nullable=False)
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
    # 구조화 요약 JSON. 구버전 레코드와 모델이 스키마를 못 지킨 경우 None이라
    # 프론트는 summary 평문으로 폴백한다.
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ChatRoom(Base):
    __tablename__ = "chat_rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # 기본은 사람끼리의 대화다. /help로 부를 때만 AI가 들어온다.
    ai_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # 방 단위 배치 스캔의 진행 지점. null이면 아직 훑은 적 없음 — 백필 불필요.
    last_scanned_message_id: Mapped[int | None] = mapped_column(nullable=True)


class ChatRoomMember(Base):
    """방에 초대된 사람. 그룹 멤버십과 별개로, 방 입장은 여기 있어야 가능하다."""

    __tablename__ = "chat_room_members"
    __table_args__ = (PrimaryKeyConstraint("room_id", "user_id"),)

    room_id: Mapped[int] = mapped_column(ForeignKey("chat_rooms.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 그룹은 방을 통해서만 안다. 여기 group_id를 함께 두면 방과 어긋날 수 있다.
    room_id: Mapped[int] = mapped_column(ForeignKey("chat_rooms.id"), nullable=False)
    sender: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_bot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


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
    # 채팅 출처 약속의 가시성 판정용. source_id(메시지)를 역참조하지 않고 방을
    # 직접 들고 있는다 — 방이 삭제되면 애플리케이션이 먼저 NULL로 만든다
    # (main.py _delete_room_cascade). ON DELETE SET NULL은 그 처리가 어떤
    # 이유로든 안 됐을 때의 최후 안전망이지 주 메커니즘이 아니다.
    room_id: Mapped[int | None] = mapped_column(
        ForeignKey("chat_rooms.id", ondelete="SET NULL"), nullable=True
    )
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


class CallBudget(Base):
    """하루에 쓴 Gemini 호출 수. 하루 한 행.

    스윕만 세던 장부를 전체 소비로 넓혔다. 사용자가 직접 부르는 요약·비서·채팅이
    장부에 안 잡히면, 배경 작업만 아껴봐야 한도는 그대로 소진된다.

    그룹이 아니라 전역이다 — Gemini 한도는 키가 아니라 **프로젝트** 단위라
    (quotaId: GenerateRequestsPerDayPerProjectPerModel), 그룹마다 예산을 주면
    그룹 수만큼 한도를 넘긴다. 키를 새로 발급해도 같은 프로젝트면 천장은 하나다.

    소비자별로 나눠 세지 않는다. 배분은 상한 규칙으로 하고(call_budget.claim),
    누가 얼마나 썼는지는 구조화 로그로 남긴다. 컬럼을 늘리면 소비자가 생길
    때마다 스키마가 바뀐다.

    날짜는 UTC 기준이다. 코드베이스가 전부 UTC로 저장·비교한다.
    """

    __tablename__ = "call_budget"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    calls: Mapped[int] = mapped_column(nullable=False, server_default="0")
