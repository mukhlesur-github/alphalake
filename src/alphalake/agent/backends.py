"""Snowflake-backed dependencies for the agent, all executed on ONE persona connection:
LLM = AI_COMPLETE, SQL = SEMANTIC views, retrieval = Cortex Search. Nothing runs as a superuser."""

import json
import re

from alphalake.common.config import get_settings
from alphalake.common.snowflake import connect_as_persona

INJECTION = re.compile(
    r"ignore (all |any )?(previous|prior|above) instructions|you are now|admin mode|system prompt|"
    r"disregard (the|your) (rules|instructions)", re.I)

# Which Cortex Search service a persona may use (the grant in V004 is what actually enforces it)
SEARCH_SERVICE = {"ALPHALAKE_PM": "ALPHALAKE.DOCS.SEARCH_RESTRICTED", "ALPHALAKE_ANALYST": "ALPHALAKE.DOCS.SEARCH_STANDARD"}
SEARCH_COLUMNS = ["chunk_text", "title", "section_title", "page_number", "doc_id", "doc_type", "fund_ticker",
                  "access_tier"]


class SnowflakeBackend:
    def __init__(self, role: str):
        self.role = role
        self.conn = connect_as_persona(role)
        self.model = get_settings().cortex_llm_model

    def llm(self, messages: list[dict], max_tokens: int = 1200) -> str:
        # AI_COMPLETE takes one prompt string (legacy SNOWFLAKE.CORTEX.COMPLETE is blocked on new accounts),
        # so the chat turns are flattened into role-labelled sections.
        prompt = "\n\n".join(f"[{m['role'].upper()}]\n{m['content']}" for m in messages) + "\n\n[ASSISTANT]\n"
        cur = self.conn.cursor()
        row = cur.execute(
            "SELECT AI_COMPLETE(%s, %s, PARSE_JSON(%s))",
            (self.model, prompt, json.dumps({"temperature": 0, "max_tokens": max_tokens})),
        ).fetchone()
        out = row[0]  # returned as a JSON-encoded string (VARIANT), e.g. '"ok"'
        return json.loads(out) if isinstance(out, str) and out.startswith('"') else out

    def query(self, sql: str, params: dict | None = None) -> list[dict]:
        from snowflake.connector import DictCursor
        cur = self.conn.cursor(DictCursor)
        rows = cur.execute(sql, params or None).fetchall()
        return [{k.lower(): (v.isoformat() if hasattr(v, "isoformat") else float(v) if hasattr(v, "as_tuple") else v)
                 for k, v in r.items()} for r in rows]

    def search(self, query: str, fund_ticker: str | None = None, limit: int = 6) -> list[dict]:
        body = {"query": query, "columns": SEARCH_COLUMNS, "limit": limit}
        if fund_ticker:
            body["filter"] = {"@eq": {"fund_ticker": fund_ticker}}
        cur = self.conn.cursor()
        row = cur.execute("SELECT SNOWFLAKE.CORTEX.SEARCH_PREVIEW(%s, %s)",
                          (SEARCH_SERVICE[self.role], json.dumps(body))).fetchone()
        return json.loads(row[0]).get("results", [])

    def audit(self, record: dict) -> None:
        self.conn.cursor().execute(
            """INSERT INTO ALPHALAKE.AUDIT.AGENT_INTERACTIONS
               (role_name, question, mode, route, sql_text, citations, answer, guardrail_flags, latency_ms)
               SELECT %s, %s, %s, %s, PARSE_JSON(%s), PARSE_JSON(%s), %s, PARSE_JSON(%s), %s""",
            (self.role, record["question"], record["mode"], record["route"], json.dumps(record["sql"]),
             json.dumps(record["citations"]), record["answer"], json.dumps(record["flags"]), record["latency_ms"]),
        )
