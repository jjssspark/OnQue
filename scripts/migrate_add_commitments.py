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
