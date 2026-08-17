"""sweep_budget 테이블을 call_budget으로 개명한다.

장부의 의미가 "스윕이 쓴 수"에서 "전체 소비"로 넓어졌다. 이름을 두면
거짓말이 되고, 나중에 읽는 사람이 사용자 호출은 안 세는 줄 안다.

행 구조는 그대로다(day PK, calls). 개명만 하므로 데이터 손실이 없다.
되돌리려면 반대 방향으로 ALTER 하면 된다.

이미 call_budget이 있으면(재실행) 아무것도 하지 않는다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, text  # noqa: E402

from db import Base, engine  # noqa: E402
import models  # noqa: E402,F401  ─ create_all이 테이블을 알려면 import가 필요하다

with engine.begin() as conn:
    tables = set(inspect(conn).get_table_names())

    if "call_budget" in tables:
        action = "이미 개명됨"
    elif "sweep_budget" in tables:
        conn.execute(text("ALTER TABLE sweep_budget RENAME TO call_budget"))
        action = "sweep_budget -> call_budget"
    else:
        action = "둘 다 없음 — create_all이 새로 만든다"

# 개명 후(또는 둘 다 없을 때) 누락 테이블을 채운다.
Base.metadata.create_all(bind=engine)

with engine.begin() as conn:
    after = set(inspect(conn).get_table_names())
    rows = conn.execute(text("SELECT count(*) FROM call_budget")).scalar()

print(action)
print(f"call_budget 행: {rows}")

assert "call_budget" in after, "call_budget 테이블이 없다"
assert "sweep_budget" not in after, "sweep_budget이 남아 있다"
