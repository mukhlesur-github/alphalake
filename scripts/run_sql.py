"""Run a .sql file as the pipeline user and print every result set (used by `make verify`, `make backfill`)."""

import sys

from alphalake.common.migrate import statements
from alphalake.common.snowflake import connect_pipeline

cur = connect_pipeline().cursor()
for stmt in statements(open(sys.argv[1]).read()):
    cur.execute(stmt)
    if cur.description:
        cols = [c[0] for c in cur.description]
        rows = cur.fetchall()
        print(f"\n-- {stmt.splitlines()[0][:100]}")
        print(" | ".join(cols))
        for r in rows[:25]:
            print(" | ".join(str(v) for v in r))
