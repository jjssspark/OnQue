"""자율 약속 추적 마이그레이션.

실행 순서 (반드시 이 순서로 — 서버 기동 후 실행하면 안 된다):
1. 이 스크립트를 먼저 실행해 기존 chat_rooms/groups 테이블에 컬럼을 추가한다.
2. 그 다음에 새 코드를 배포한다. clients/commitments 같은 신규 테이블은
   서버가 기동하며 main.py의 Base.metadata.create_all이 만든다.

순서가 중요한 이유: 여기서 추가하는 컬럼은 전부 nullable이라 구버전 코드에
무해하다 — 모르는 컬럼은 그냥 무시한다. 하지만 반대로 새 코드를 먼저
배포하면, SQLAlchemy가 매핑된 모든 컬럼을 SELECT에 담기 때문에 DB에 컬럼이
없는 동안 groups나 chat_rooms를 건드리는 모든 쿼리가 실패한다 — 신규
기능만이 아니라 그룹·채팅 전체가 죽는다. TS-016에 기록된 것과 같은 실패
모드다. 마이그레이션을 먼저 돌려야 이 창이 아예 생기지 않는다.

두 컬럼 모두 nullable이고 null이 "아직 없음"을 뜻한다. last_swept_at은
null이면 다음 조회에서 스윕이 한 번 돌 뿐이라 백필이 필요 없다. 반면
last_scanned_message_id는 null이면 방 전체가 "미스캔"으로 취급되어 첫
스윕이 그 방의 채팅 역사 전체를 100개씩 훑게 된다 — Gemini 호출을
낭비하고 몇 달 전에 끝난 프로젝트의 약속까지 검토 큐에 쏟아낸다. 그래서
이 컬럼만은 기존 방의 포인터를 "지금까지의 최신 메시지"로 시딩해
스캔이 배포 시점부터 시작하게 만든다. 메시지가 없는 방은 MAX가 NULL을
돌려주므로 그대로 미스캔 취급되고, 이는 해가 없다.
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


def _table_exists(conn, table: str) -> bool:
    result = conn.execute(
        text("SELECT 1 FROM information_schema.tables WHERE table_name = :table"),
        {"table": table},
    )
    return result.first() is not None


def main() -> None:
    with engine.begin() as conn:
        if not _column_exists(conn, "chat_rooms", "last_scanned_message_id"):
            conn.execute(
                text("ALTER TABLE chat_rooms ADD COLUMN last_scanned_message_id INTEGER")
            )
            # 이 UPDATE는 멱등하지 않다 — 컬럼을 막 추가한 이 분기 안에서만
            # 실행돼야 한다. 이미 컬럼이 있는 재실행 경로(else)에서 돌리면
            # 그 사이 쌓인 실제 스캔 진행 상황을 최신 메시지로 덮어써 버린다.
            conn.execute(
                text(
                    "UPDATE chat_rooms SET last_scanned_message_id = "
                    "(SELECT MAX(id) FROM chat_messages WHERE room_id = chat_rooms.id)"
                )
            )
            print("chat_rooms.last_scanned_message_id 추가 + 기존 방 포인터를 최신 메시지로 시딩")
        else:
            print("chat_rooms.last_scanned_message_id 이미 있음")

        if not _column_exists(conn, "groups", "last_swept_at"):
            conn.execute(
                text("ALTER TABLE groups ADD COLUMN last_swept_at TIMESTAMPTZ")
            )
            print("groups.last_swept_at 추가")
        else:
            print("groups.last_swept_at 이미 있음")

        # commitments는 신규 테이블이다. 정상적인 흐름(이 스크립트 실행 →
        # 배포 → main.py의 create_all)이면 이 시점에 아직 존재하지 않고,
        # create_all이 room_id까지 포함해서 만든다 — ALTER를 시도하면
        # "테이블이 없다" 에러만 난다. 따라서 테이블이 이미 존재하는
        # 경우(재실행, 또는 순서를 어기고 배포부터 한 경우)에만 손댄다.
        if _table_exists(conn, "commitments"):
            if not _column_exists(conn, "commitments", "room_id"):
                conn.execute(
                    text(
                        "ALTER TABLE commitments ADD COLUMN room_id INTEGER "
                        "REFERENCES chat_rooms(id) ON DELETE SET NULL"
                    )
                )
                print("commitments.room_id 추가")
            else:
                print("commitments.room_id 이미 있음")
        else:
            print("commitments 테이블 없음 — create_all이 room_id까지 함께 만든다")


if __name__ == "__main__":
    main()
