"""Minimal versioned migration runner (schemachange-style): V###__name.sql applied once, in order.

Files are Jinja-rendered with {bucket, landing_mode}; applied versions + checksums live in AUDIT.MIGRATION_HISTORY.
"""

import hashlib
import io
import re

from jinja2 import Template
from snowflake.connector.util_text import split_statements

from alphalake.common.config import ROOT, get_settings

MIGRATIONS = ROOT / "snowflake" / "migrations"


def render(path) -> str:
    return Template(path.read_text()).render(bucket=get_settings().alphalake_bucket,
                                         landing_mode=get_settings().landing_mode,
                                         governance_mode=get_settings().governance_mode)


def statements(sql: str) -> list[str]:
    return [s for s, _ in split_statements(io.StringIO(sql), remove_comments=True) if s.strip()]


def migrate(dry_run: bool = False) -> None:
    files = sorted(MIGRATIONS.glob("V*__*.sql"), key=lambda p: int(re.match(r"V(\d+)", p.name).group(1)))
    if dry_run:
        for f in files:
            print(f"{f.name}: {len(statements(render(f)))} statements")
        return
    if get_settings().landing_mode == "s3" and not get_settings().alphalake_bucket:
        raise SystemExit("ALPHALAKE_BUCKET is empty -- run `make tf-output` first")

    from alphalake.common.snowflake import connect_pipeline
    conn = connect_pipeline()
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS ALPHALAKE.AUDIT.MIGRATION_HISTORY (
        version NUMBER, script STRING, checksum STRING, applied_at TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP())""")
    applied = {r[0]: r[1] for r in cur.execute("SELECT version, checksum FROM ALPHALAKE.AUDIT.MIGRATION_HISTORY")}
    for f in files:
        version = int(re.match(r"V(\d+)", f.name).group(1))
        sql = render(f)
        checksum = hashlib.sha256(sql.encode()).hexdigest()
        if version in applied:
            if applied[version] != checksum:
                print(f"WARNING {f.name} changed after being applied -- write a new V### migration instead")
            continue
        print(f"applying {f.name}")
        for stmt in statements(sql):
            cur.execute(stmt)
        cur.execute("INSERT INTO ALPHALAKE.AUDIT.MIGRATION_HISTORY (version, script, checksum) VALUES (%s, %s, %s)",
                    (version, f.name, checksum))
    print("migrations up to date")
