"""group_invitations 테이블 생성.

추가 전용이다. 기존 데이터를 옮기지 않으므로 백필이 없고, 되돌리려면 이 테이블만
지우면 된다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, text  # noqa: E402

from db import Base, engine  # noqa: E402
import models  # noqa: E402,F401  ─ create_all이 테이블을 알려면 import가 필요하다

Base.metadata.create_all(bind=engine)

assert inspect(engine).has_table("group_invitations"), "테이블이 만들어지지 않았다."

with engine.connect() as conn:
    rows = conn.execute(text("SELECT count(*) FROM group_invitations")).scalar()

print(f"group_invitations 준비 완료 (현재 {rows}행)")
