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
            conn.execute(
                text(
                    "ALTER TABLE group_memberships "
                    "ADD CONSTRAINT ck_group_memberships_role CHECK (role IN ('admin', 'member'))"
                )
            )
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
