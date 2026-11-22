"""Governed text-to-SQL (advanced mode): the LLM writes SQL, sqlglot decides whether it may run.

Rules: exactly one statement; read-only query; every table is a SEMANTIC.* view (or a CTE); row limit
enforced. Execution still happens under the end user's role, so masking/row access apply on top.
"""

import sqlglot
from sqlglot import exp

ALLOWED_SCHEMA = "SEMANTIC"
MAX_ROWS = 200
FORBIDDEN = (exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop, exp.Alter, exp.Command,
             exp.Copy, exp.TruncateTable, exp.Grant)


class UnsafeSQL(ValueError):
    pass


def validate(sql: str) -> str:
    try:
        stmts = [s for s in sqlglot.parse(sql, read="snowflake") if s is not None]
    except sqlglot.errors.ParseError as e:
        raise UnsafeSQL(f"could not parse SQL: {e}") from e
    if len(stmts) != 1:
        raise UnsafeSQL("exactly one statement is allowed")
    tree = stmts[0]
    if not isinstance(tree, exp.Query):
        raise UnsafeSQL(f"only SELECT queries are allowed, got {type(tree).__name__}")
    for node in tree.walk():
        if isinstance(node, FORBIDDEN):
            raise UnsafeSQL(f"{type(node).__name__} is not allowed")
    ctes = {c.alias_or_name.upper() for c in tree.find_all(exp.CTE)}
    for t in tree.find_all(exp.Table):
        name, db, catalog = t.name.upper(), t.db.upper(), t.catalog.upper()
        if not db and name in ctes:
            continue
        if db != ALLOWED_SCHEMA or catalog not in ("", "ALPHALAKE"):
            raise UnsafeSQL(f"table {t.sql()} is outside {ALLOWED_SCHEMA}.*")
    if isinstance(tree, exp.Select | exp.Union):
        limit = tree.args.get("limit")
        current = None
        if limit is not None and isinstance(limit.expression, exp.Literal):
            current = int(limit.expression.this)
        if current is None or current > MAX_ROWS:
            tree = tree.limit(MAX_ROWS)
    return tree.sql(dialect="snowflake")
