"""chat_room_members 테이블 생성 + 기존 방에 그룹원 전원 백필.

방 접근 규칙이 "그룹원이면 누구나"에서 "초대된 사람만"으로 바뀐다. 백필하지 않으면
배포 즉시 기존 방이 전부 멤버 0명이 되어 아무도 들어가지 못한다.

추가 전용이다. 기존 테이블을 건드리지 않으므로 되돌리려면 이 테이블만 지우면 된다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from db import Base, engine  # noqa: E402
import models  # noqa: E402,F401  ─ create_all이 테이블을 알려면 import가 필요하다

Base.metadata.create_all(bind=engine)

with engine.begin() as conn:
    before = conn.execute(text("SELECT count(*) FROM chat_room_members")).scalar()

    # 그룹원 × 그 그룹의 방. 이미 있는 행은 건드리지 않는다.
    inserted = conn.execute(
        text(
            """
            INSERT INTO chat_room_members (room_id, user_id)
            SELECT r.id, m.user_id
            FROM chat_rooms r
            JOIN group_memberships m ON m.group_id = r.group_id
            ON CONFLICT (room_id, user_id) DO NOTHING
            """
        )
    ).rowcount

    after = conn.execute(text("SELECT count(*) FROM chat_room_members")).scalar()
    orphan = conn.execute(
        text(
            """
            SELECT count(*) FROM chat_rooms r
            WHERE NOT EXISTS (
                SELECT 1 FROM chat_room_members cm WHERE cm.room_id = r.id
            )
            """
        )
    ).scalar()

print(f"chat_room_members: {before} → {after} (신규 {inserted}행)")
print(f"멤버 없는 방: {orphan}개")
assert orphan == 0, "멤버가 없는 방이 남았다. 그룹원이 0명인 그룹이 있는지 확인할 것."
