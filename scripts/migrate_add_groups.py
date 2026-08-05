"""그룹 구조 도입 마이그레이션.

실행 순서:
1. 서버를 한 번 기동해 users/groups/group_memberships/announcements 테이블을 만든다
   (main.py의 Base.metadata.create_all이 신규 테이블만 생성한다).
2. POST /api/v1/auth/signup 으로 최초 관리자 계정을 만든다.
3. 이 스크립트를 실행한다 — 기존 todos/chat_messages/schedules/documents 테이블에
   group_id 컬럼과 FK 제약을 추가하고, 이미 있던 레코드를 모두 "기본 그룹"으로 이관한다.

schedules/documents의 group_id는 앞으로 "전사 공용"을 뜻하는 NULL을 허용하지만,
마이그레이션 이전 데이터는 전사 공용이 아니라 기존 사용자들이 쓰던 데이터이므로
기본 그룹으로 백필한다. 백필하지 않으면 documents는 list_documents 쿼리
(group_id = :gid OR (is_template AND group_id IS NULL))의 어느 쪽에도 걸리지 않아
영구히 보이지 않게 되고, schedules는 관리자만 수정/삭제할 수 있게 되어
마이그레이션 전 동작이 바뀐다.
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


def _constraint_exists(conn, table: str, constraint: str) -> bool:
    result = conn.execute(
        text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_name = :table AND constraint_name = :constraint"
        ),
        {"table": table, "constraint": constraint},
    )
    return result.first() is not None


def _add_missing_foreign_keys() -> None:
    with engine.begin() as conn:
        for table in ("todos", "chat_messages", "schedules", "documents"):
            constraint = f"fk_{table}_group_id"
            if _constraint_exists(conn, table, constraint):
                continue
            conn.execute(
                text(
                    f"ALTER TABLE {table} ADD CONSTRAINT {constraint} "
                    "FOREIGN KEY (group_id) REFERENCES groups(id)"
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
        db.execute(
            text("UPDATE schedules SET group_id = :gid WHERE group_id IS NULL"),
            {"gid": default_group.id},
        )
        db.execute(
            text("UPDATE documents SET group_id = :gid WHERE group_id IS NULL"),
            {"gid": default_group.id},
        )
        db.commit()
        return default_group.id
    finally:
        db.close()


def _enforce_not_null() -> None:
    """schedules/documents는 앞으로 NULL(전사 공용)을 허용해야 하므로 제외한다."""
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE todos ALTER COLUMN group_id SET NOT NULL"))
        conn.execute(text("ALTER TABLE chat_messages ALTER COLUMN group_id SET NOT NULL"))


def main() -> None:
    _add_missing_columns()
    _add_missing_foreign_keys()
    default_group_id = _backfill_default_group()
    if default_group_id is None:
        return
    _enforce_not_null()
    print(f"마이그레이션 완료. 기본 그룹 id={default_group_id}")


if __name__ == "__main__":
    main()
