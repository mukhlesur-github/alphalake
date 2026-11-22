"""Single CLI entry point: `uv run alphalake <command>`."""

import argparse


def main() -> None:
    p = argparse.ArgumentParser(prog="alphalake")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("generate", help="write synthetic batch + trade history files to data/landing")
    sub.add_parser("generate-docs", help="write synthetic PDFs to data/docs/raw")
    sub.add_parser("parse-docs", help="parse PDFs -> chunked JSON in data/landing/docs/parsed (SHA-256 sync)")
    up = sub.add_parser("upload", help="sync data/landing -> s3://<bucket>/landing")
    up.add_argument("--prefix", default="", help="only upload keys under this prefix, e.g. batch/securities")
    st = sub.add_parser("stream", help="produce live trade events as micro-batch files")
    st.add_argument("--rate", type=float, default=5, help="new trades per second")
    st.add_argument("--seconds", type=int, default=120)
    st.add_argument("--flush", type=int, default=10, help="seconds per micro-batch file")
    st.add_argument("--local", action="store_true", help="write to data/landing instead of S3")
    mg = sub.add_parser("migrate", help="apply snowflake/migrations/V*.sql in order")
    mg.add_argument("--dry-run", action="store_true")
    sub.add_parser("smoke", help="check Snowflake key-pair auth, Cortex embed + complete, S3 access")
    ask = sub.add_parser("ask", help="ask the agent a question from the terminal")
    ask.add_argument("question")
    ask.add_argument("--role", default="ALPHALAKE_PM")
    ask.add_argument("--mode", choices=["tool", "sql"], default="tool")
    a = p.parse_args()

    if a.cmd == "generate":
        from alphalake.generators.run import generate
        generate()
    elif a.cmd == "generate-docs":
        from alphalake.generators.documents import generate_documents
        generate_documents()
    elif a.cmd == "parse-docs":
        from alphalake.docs.pipeline import parse_all
        parse_all()
    elif a.cmd == "upload":
        from alphalake.producers.upload import upload
        upload(a.prefix)
    elif a.cmd == "stream":
        from alphalake.producers.stream import stream
        stream(rate=a.rate, seconds=a.seconds, flush=a.flush, local=a.local)
    elif a.cmd == "migrate":
        from alphalake.common.migrate import migrate
        migrate(dry_run=a.dry_run)
    elif a.cmd == "smoke":
        from alphalake.common.smoke import smoke
        smoke()
    elif a.cmd == "ask":
        from alphalake.agent.graph import ask
        r = ask(a.question, role=a.role, mode=a.mode)
        print(r["answer"])
        for c in r.get("citations", []):
            print(f"  [{c['n']}] {c['title']} p.{c['page']}")
        for q in r.get("sql", []):
            print("  SQL:", q)


if __name__ == "__main__":
    main()
