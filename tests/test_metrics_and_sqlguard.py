import pytest
from pydantic import ValidationError

from alphalake.agent.metrics import compile_call
from alphalake.agent.sqlguard import UnsafeSQL, validate


def test_exposure_compiles_to_parameterised_sql():
    sql, params = compile_call("exposure", {"fund_ticker": "GTIF", "dimension": "gics_sub_industry"})
    assert "gics_sub_industry AS bucket" in sql and "%(fund_ticker)s" in sql
    assert params["fund_ticker"] == "GTIF" and params["as_of_date"] is None
    assert "GTIF" not in sql  # values are bound, never interpolated


@pytest.mark.parametrize("args", [
    {"fund_ticker": "GTIF", "dimension": "name; DROP TABLE x"},
    {"fund_ticker": "NOPE"},
    {"fund_ticker": "GTIF", "top_n": 10_000},
])
def test_invalid_tool_args_rejected(args):
    with pytest.raises(ValidationError):
        compile_call("exposure", args)


def test_unknown_metric_rejected():
    with pytest.raises(ValueError):
        compile_call("drop_everything", {})


def test_sqlguard_allows_semantic_select_and_adds_limit():
    out = validate("SELECT fund_ticker, SUM(weight_pct) FROM SEMANTIC.HOLDINGS GROUP BY 1")
    assert out.upper().endswith("LIMIT 200")


def test_sqlguard_allows_ctes_over_semantic():
    validate("WITH x AS (SELECT * FROM ALPHALAKE.SEMANTIC.HOLDINGS) SELECT * FROM x LIMIT 5")


@pytest.mark.parametrize("sql", [
    "SELECT * FROM GOLD.DIM_CLIENT",
    "SELECT * FROM BRONZE.CLIENTS_RAW",
    "SELECT * FROM HOLDINGS",
    "DELETE FROM SEMANTIC.HOLDINGS",
    "SELECT 1; DROP TABLE SEMANTIC.HOLDINGS",
    "SELECT * FROM SEMANTIC.HOLDINGS h JOIN SILVER.TRADES_CURRENT t ON 1=1",
    "SELECT * FROM (SELECT * FROM GOLD.FACT_DAILY_HOLDINGS)",
    "GRANT ROLE ACCOUNTADMIN TO USER X",
])
def test_sqlguard_rejects(sql):
    with pytest.raises(UnsafeSQL):
        validate(sql)
