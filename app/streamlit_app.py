"""AlphaLake Streamlit app (local). Every query runs under the persona chosen in the sidebar,
so masking, row access and document tiers visibly change what the same question returns."""

import altair as alt
import pandas as pd
import streamlit as st

from alphalake.agent.graph import ask
from alphalake.common.snowflake import PERSONA_ROLES, connect_as_persona, connect_pipeline

# Reference palette (dataviz skill): one series hue, recessive ink, reserved status colours.
BLUE, INK_2, MUTED, CRITICAL, GOOD = "#2a78d6", "#52514e", "#898781", "#d03b3b", "#0ca30c"

st.set_page_config(page_title="AlphaLake", layout="wide")


@st.cache_resource
def persona_conn(role: str):
    return connect_as_persona(role)


@st.cache_resource
def engineer_conn():
    return connect_pipeline()


def q(sql: str, params=None, role: str | None = None) -> pd.DataFrame:
    conn = engineer_conn() if role is None else persona_conn(role)
    cur = conn.cursor()
    cur.execute(sql, params)
    df = cur.fetch_pandas_all()
    df.columns = [c.lower() for c in df.columns]
    return df


def axis_theme(chart):
    return chart.configure_axis(labelColor=INK_2, titleColor=INK_2, gridColor="#e9e8e4", domainColor=MUTED,
                                tickColor=MUTED).configure_view(strokeWidth=0)


with st.sidebar:
    st.title("AlphaLake")
    role = st.radio("Persona (Snowflake role)", PERSONA_ROLES, help="All queries run under this role")
    st.caption("PM: PII visible, restricted documents searchable.  \nAnalyst: PII masked, no institutional "
               "clients, no restricted documents.")

tab_overview, tab_fund, tab_ask, tab_clients, tab_pipeline = st.tabs(
    ["Overview", "Fund detail", "Ask AlphaLake", "Clients (governance)", "Pipeline"])

with tab_overview:
    nav = q("SELECT * FROM SEMANTIC.FUND_NAV WHERE as_of_date = (SELECT MAX(as_of_date) FROM SEMANTIC.FUND_NAV)",
            role=role)
    comp = q("SELECT * FROM SEMANTIC.COMPLIANCE WHERE as_of_date = (SELECT MAX(as_of_date) FROM SEMANTIC.COMPLIANCE)",
             role=role)
    c1, c2, c3 = st.columns(3)
    c1.metric("Firm AUM (USD)", f"${nav.net_asset_value_usd.sum() / 1e9:,.2f}B")
    c2.metric("Funds", len(nav))
    c3.metric("Limit breaches today", int(comp.is_breach.sum()))
    st.caption(f"As of {nav.as_of_date.max()}")
    st.subheader("Net asset value by fund")
    bars = alt.Chart(nav).mark_bar(color=BLUE, cornerRadiusEnd=4, size=14).encode(
        x=alt.X("net_asset_value_usd:Q", title="NAV (USD)", axis=alt.Axis(format="~s")),
        y=alt.Y("fund_ticker:N", sort="-x", title=None),
        tooltip=["fund_ticker", "fund_name", alt.Tooltip("net_asset_value_usd:Q", format=",.0f", title="NAV USD"),
                 "manager_name"])
    st.altair_chart(axis_theme(bars), use_container_width=True)
    st.subheader("Mandate limit checks")
    comp["status"] = comp.is_breach.map({True: "⛔ Breach", False: "✅ Within limit"})
    st.dataframe(comp[["fund_ticker", "limit_type", "bucket", "actual_pct", "limit_pct", "headroom_pct", "status"]],
                 hide_index=True, use_container_width=True)

with tab_fund:
    fund = st.selectbox("Fund", ["GTIF", "EUTF", "USLG", "USLV", "ESGL", "EMEQ", "DIVI", "GBND", "HYLD", "MUNI",
                                 "BAL6", "MMKT"])
    dim = st.radio("Exposure by", ["gics_sub_industry", "gics_sector", "country"], horizontal=True)
    expo = q(f"""SELECT {dim} AS bucket, SUM(weight_pct) AS exposure_pct, SUM(market_value_usd) AS mv
                 FROM SEMANTIC.HOLDINGS WHERE fund_ticker = %s
                 AND as_of_date = (SELECT MAX(as_of_date) FROM SEMANTIC.HOLDINGS) GROUP BY 1""", (fund,), role=role)
    st.altair_chart(axis_theme(alt.Chart(expo).mark_bar(color=BLUE, cornerRadiusEnd=4, size=14).encode(
        x=alt.X("exposure_pct:Q", title="% of NAV"), y=alt.Y("bucket:N", sort="-x", title=None),
        tooltip=["bucket", alt.Tooltip("exposure_pct:Q", format=".2f", title="% of NAV"),
                 alt.Tooltip("mv:Q", format=",.0f", title="USD")])), use_container_width=True)

    limits = q("SELECT DISTINCT limit_type, dimension, bucket, limit_pct FROM SEMANTIC.COMPLIANCE "
               "WHERE fund_ticker = %s AND dimension = 'gics_sub_industry'", (fund,), role=role)
    if not limits.empty:
        lim = limits.iloc[0]
        st.subheader(f"{lim.bucket} exposure over time vs {lim.limit_pct:.0f}% limit")
        hist = q("""SELECT as_of_date, actual_pct FROM SEMANTIC.COMPLIANCE
                    WHERE fund_ticker = %s AND limit_type = %s ORDER BY 1""", (fund, lim.limit_type), role=role)
        hover = alt.selection_point(fields=["as_of_date"], nearest=True, on="pointerover", empty=False)
        base = alt.Chart(hist).encode(x=alt.X("as_of_date:T", title=None))
        line = base.mark_line(color=BLUE, strokeWidth=2).encode(y=alt.Y("actual_pct:Q", title="% of NAV"))
        rule = alt.Chart(pd.DataFrame({"y": [lim.limit_pct]})).mark_rule(color=MUTED, strokeDash=[4, 4]).encode(y="y:Q")
        label = alt.Chart(pd.DataFrame({"y": [lim.limit_pct], "t": [f"Limit {lim.limit_pct:.0f}%"]})).mark_text(
            align="left", dx=4, dy=-6, color=INK_2).encode(y="y:Q", text="t:N", x=alt.value(0))
        pts = base.mark_point(size=80, filled=True, color=BLUE).encode(
            y="actual_pct:Q", opacity=alt.condition(hover, alt.value(1), alt.value(0)),
            tooltip=[alt.Tooltip("as_of_date:T"), alt.Tooltip("actual_pct:Q", format=".2f", title="% of NAV")]
        ).add_params(hover)
        st.altair_chart(axis_theme(line + rule + label + pts), use_container_width=True)
        with st.expander("Table view"):
            st.dataframe(hist, hide_index=True)

with tab_ask:
    mode = st.radio("SQL mode", ["tool", "sql"], horizontal=True,
                    format_func=lambda m: "Tool calling (default)" if m == "tool" else "Governed text-to-SQL")
    question = st.text_input("Question", "Is the Global Tech Innovation Fund within its semiconductor limit, "
                                         "and what did the manager say about it?")
    if st.button("Ask", type="primary") and question:
        with st.spinner(f"Thinking as {role}..."):
            r = ask(question, role=role, mode=mode)
        st.markdown(r["answer"])
        for c in r["citations"]:
            st.caption(f"[{c['n']}] {c['title']}, page {c['page']} ({c['access_tier']})")
        cols = st.columns(3)
        cols[0].caption(f"Route: **{r['route']}** · {r['latency_ms']} ms")
        if r["flags"]:
            cols[1].warning("Guardrail flags: " + ", ".join(r["flags"]))
        for sql in r["sql"]:
            with st.expander("SQL executed (under your role)"):
                st.code(sql, language="sql")
        for res in r["results"]:
            with st.expander(f"Result: {res['metric']}"):
                st.dataframe(pd.DataFrame(res["rows"]), hide_index=True)
        if r["chunks"]:
            with st.expander(f"Retrieved passages ({len(r['chunks'])})"):
                for i, c in enumerate(r["chunks"], 1):
                    st.markdown(f"**[{i}] {c.get('title')}**, {c.get('section_title')}, p.{c.get('page_number')}")
                    st.text(c.get("chunk_text", "")[:800])

with tab_clients:
    st.caption("Same query, different persona: masking policy on PII columns, row access policy on segment.")
    df = q("SELECT client_id, first_name, last_name, email, tax_id, segment, fund_ticker, units "
           "FROM GOLD.DIM_CLIENT WHERE is_current ORDER BY client_id LIMIT 50", role=role)
    st.dataframe(df, hide_index=True, use_container_width=True)
    seg = q("SELECT segment, COUNT(*) AS clients FROM GOLD.DIM_CLIENT WHERE is_current GROUP BY 1", role=role)
    st.dataframe(seg, hide_index=True)

with tab_pipeline:
    st.caption("Engineer view (ALPHALAKE_ENGINEER), shown regardless of persona.")
    st.subheader("Task runs (last 24h)")
    st.dataframe(q("""SELECT name, state, scheduled_time, completed_time, return_value, error_message
        FROM TABLE(ALPHALAKE.INFORMATION_SCHEMA.TASK_HISTORY(
            SCHEDULED_TIME_RANGE_START => DATEADD(hour, -24, CURRENT_TIMESTAMP()), RESULT_LIMIT => 50))
        WHERE state <> 'SKIPPED' ORDER BY scheduled_time DESC"""), hide_index=True, use_container_width=True)
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Quarantine")
        st.dataframe(q("SELECT reason, COUNT(*) n FROM ALPHALAKE.SILVER.QUARANTINE_TRADE_EVENTS GROUP BY 1 "
                       "UNION ALL SELECT reason, COUNT(*) FROM ALPHALAKE.SILVER.QUARANTINE_SECURITIES GROUP BY 1"),
                     hide_index=True)
        st.subheader("Recon breaks (custodian vs books)")
        st.dataframe(q("SELECT break_type, COUNT(*) n FROM ALPHALAKE.GOLD.FACT_HOLDINGS_RECONCILIATION "
                       "WHERE is_break GROUP BY 1"), hide_index=True)
    with c2:
        st.subheader("Trades by status")
        st.dataframe(q("SELECT status, COUNT(*) n FROM ALPHALAKE.SILVER.TRADES_CURRENT GROUP BY 1 ORDER BY 2 DESC"),
                     hide_index=True)
        st.subheader("Documents")
        st.dataframe(q("SELECT doc_id, version, access_tier, chunk_count, pii_redactions FROM ALPHALAKE.DOCS.DOCUMENTS "
                       "ORDER BY doc_id"), hide_index=True)
    st.subheader("Recent agent interactions")
    st.dataframe(q("SELECT ts, role_name, mode, route, question, latency_ms, guardrail_flags "
                   "FROM ALPHALAKE.AUDIT.AGENT_INTERACTIONS ORDER BY ts DESC LIMIT 20"), hide_index=True)
