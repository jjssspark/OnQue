"""groups에 직전 스윕 성과 컬럼 2개 추가 + sweep_budget 테이블 생성.

스윕은 조용히 돌아서 사용자가 AI가 일하고 있다는 걸 모른다. last_swept_at은
언제 돌았는지만 알려주고 "무엇을 얼마나 했는지"는 어디에도 안 남아, 화면에
"대화 34개에서 2건 찾음"을 띄울 수 없었다.

추가 전용이다. 기존 컬럼과 행을 건드리지 않는다. 되돌리려면 두 컬럼과
sweep_budget 테이블을 지우면 된다.

백필하지 않는다. 이 두 값은 "직전 스윕"의 성과라 과거를 소급할 수 없고,
NULL은 "아직 한 번도 안 돌았음"이라는 뜻으로 화면에서 그대로 쓰인다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, text  # noqa: E402

from db import Base, engine  # noqa: E402
import models  # noqa: E402,F401  ─ create_all이 테이블을 알려면 import가 필요하다

# sweep_budget은 신규 테이블이라 create_all이 만든다.
Base.metadata.create_all(bind=engine)

NEW_COLUMNS = {
    "last_sweep_scanned": "INTEGER",
    "last_sweep_found": "INTEGER",
}

with engine.begin() as conn:
    existing = {c["name"] for c in inspect(conn).get_columns("groups")}

    added = []
    for name, sql_type in NEW_COLUMNS.items():
        if name in existing:
            continue
        # IF NOT EXISTS를 쓰지 않는 이유: 위에서 이미 확인했고, 지원 여부가
        # DB 버전마다 갈린다. 확인 후 실행이 어느 쪽에서든 똑같이 동작한다.
        conn.execute(text(f"ALTER TABLE groups ADD COLUMN {name} {sql_type}"))
        added.append(name)

    after = {c["name"] for c in inspect(conn).get_columns("groups")}
    budget_rows = conn.execute(text("SELECT count(*) FROM sweep_budget")).scalar()

print(f"groups 컬럼 추가: {added or '(이미 있음)'}")
print(f"sweep_budget 행: {budget_rows}")

missing = set(NEW_COLUMNS) - after
assert not missing, f"컬럼이 만들어지지 않았다: {missing}"
