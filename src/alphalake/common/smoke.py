"""`alphalake smoke`: verify every integration handshake once, with a clear pass/fail per check."""

from alphalake.common.config import get_settings


def _check(name, fn):
    try:
        print(f"PASS {name}: {fn()}")
        return True
    except Exception as e:  # noqa: BLE001 -- report every failure, don't stop at the first
        print(f"FAIL {name}: {type(e).__name__}: {str(e).splitlines()[0][:200]}")
        return False


def smoke() -> None:
    s = get_settings()
    from alphalake.common.snowflake import connect_as_persona, connect_pipeline

    def pipeline():
        c = connect_pipeline().cursor()
        return c.execute("SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE()").fetchone()

    def persona():
        c = connect_as_persona("ALPHALAKE_ANALYST").cursor()
        return c.execute("SELECT CURRENT_ROLE(), CURRENT_SECONDARY_ROLES()").fetchone()

    def embed():
        c = connect_pipeline().cursor()
        v = c.execute("SELECT SNOWFLAKE.CORTEX.EMBED_TEXT_1024('snowflake-arctic-embed-l-v2.0', 'hello')").fetchone()[0]
        return f"vector dim {len(v)}"

    def complete():
        c = connect_pipeline().cursor()
        return c.execute("SELECT SNOWFLAKE.CORTEX.COMPLETE(%s, 'Reply with the single word ok')",
                         (s.cortex_llm_model,)).fetchone()[0].strip()[:40]

    def stage():
        c = connect_pipeline().cursor()
        rows = c.execute("LIST @ALPHALAKE.BRONZE.LANDING PATTERN='.*fund_limits.*'").fetchall()
        return f"storage integration OK, {len(rows)} file(s) visible"

    def s3():
        from alphalake.producers.upload import s3_client
        s3_client().head_bucket(Bucket=s.alphalake_bucket)
        return f"s3://{s.alphalake_bucket} reachable with profile {s.aws_profile}"

    ok = [_check(n, f) for n, f in [("snowflake pipeline key-pair", pipeline), ("snowflake app persona", persona),
                                    ("cortex embed", embed), (f"cortex complete ({s.cortex_llm_model})", complete),
                                    ("aws s3", s3), ("external stage", stage)]]
    raise SystemExit(0 if all(ok) else 1)
