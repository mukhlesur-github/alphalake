"""Governed metric catalogue = the agent's tool schema (default SQL mode).

The LLM only picks a metric and fills typed arguments; Python compiles deterministic, parameterised SQL
against SEMANTIC.* views. Dimension names are enums mapped to columns, so nothing the LLM writes is ever
interpolated into SQL text.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Dimension = Literal["gics_sector", "gics_sub_industry", "country", "ticker"]
FUND_TICKERS = ("GTIF", "EUTF", "USLG", "USLV", "ESGL", "EMEQ", "DIVI", "GBND", "HYLD", "MUNI", "BAL6", "MMKT")
FundTicker = Literal[FUND_TICKERS]  # type: ignore[valid-type]

_LATEST = "(SELECT MAX(as_of_date) FROM SEMANTIC.HOLDINGS WHERE as_of_date <= COALESCE(%(as_of_date)s, CURRENT_DATE()))"


class Exposure(BaseModel):
    """Exposure (% of NAV and USD) of one fund by sector, sub-industry, country or security on a date."""
    fund_ticker: FundTicker
    dimension: Dimension = "gics_sector"
    as_of_date: date | None = Field(None, description="omit for the latest available date")
    top_n: int = Field(10, ge=1, le=50)

    def compile(self):
        sql = f"""SELECT as_of_date, fund_ticker, {self.dimension} AS bucket,
       ROUND(SUM(weight_pct), 2) AS exposure_pct, ROUND(SUM(market_value_usd), 0) AS market_value_usd
FROM SEMANTIC.HOLDINGS
WHERE fund_ticker = %(fund_ticker)s AND as_of_date = {_LATEST}
GROUP BY 1, 2, 3 ORDER BY exposure_pct DESC LIMIT %(top_n)s"""
        return sql, self.model_dump()


class ExposureHistory(BaseModel):
    """Month-end history of one exposure bucket for a fund, e.g. GTIF Semiconductors over time."""
    fund_ticker: FundTicker
    dimension: Dimension = "gics_sub_industry"
    bucket: str = Field(description="e.g. 'Semiconductors', 'Information Technology', 'US'")
    start_date: date | None = None
    end_date: date | None = None

    def compile(self):
        sql = f"""SELECT h.as_of_date, h.fund_ticker, ROUND(SUM(h.weight_pct), 2) AS exposure_pct
FROM SEMANTIC.HOLDINGS h
WHERE h.fund_ticker = %(fund_ticker)s AND h.{self.dimension} = %(bucket)s
  AND h.as_of_date = LAST_DAY(h.as_of_date) - CASE DAYOFWEEKISO(LAST_DAY(h.as_of_date)) WHEN 6 THEN 1 WHEN 7 THEN 2 ELSE 0 END
  AND h.as_of_date BETWEEN COALESCE(%(start_date)s, '1900-01-01'::DATE) AND COALESCE(%(end_date)s, CURRENT_DATE())
GROUP BY 1, 2 ORDER BY 1"""
        return sql, self.model_dump()


class Compliance(BaseModel):
    """Mandate limit checks (actual vs limit, breach flag, headroom) for one or all funds on a date."""
    fund_ticker: FundTicker | None = None
    as_of_date: date | None = None
    only_breaches: bool = False

    def compile(self):
        sql = f"""SELECT as_of_date, fund_ticker, limit_type, dimension, bucket, actual_pct, limit_pct, is_breach, headroom_pct
FROM SEMANTIC.COMPLIANCE
WHERE as_of_date = {_LATEST}
  AND (%(fund_ticker)s IS NULL OR fund_ticker = %(fund_ticker)s)
  AND (NOT %(only_breaches)s OR is_breach)
ORDER BY fund_ticker, limit_type"""
        return sql, self.model_dump()


class FundNav(BaseModel):
    """Net asset value (USD) per fund on a date; omit fund_ticker for all funds (firm AUM)."""
    fund_ticker: FundTicker | None = None
    as_of_date: date | None = None

    def compile(self):
        sql = f"""SELECT as_of_date, fund_ticker, fund_name, manager_name, ROUND(net_asset_value_usd, 0) AS nav_usd, positions
FROM SEMANTIC.FUND_NAV
WHERE as_of_date = {_LATEST} AND (%(fund_ticker)s IS NULL OR fund_ticker = %(fund_ticker)s)
ORDER BY nav_usd DESC"""
        return sql, self.model_dump()


class RecentTrades(BaseModel):
    """Executed trades for a fund over the last N days (cancelled trades are excluded)."""
    fund_ticker: FundTicker
    days: int = Field(7, ge=1, le=90)
    limit: int = Field(20, ge=1, le=100)

    def compile(self):
        sql = """SELECT trade_date, ticker, security_name, side, filled_qty, ROUND(avg_fill_price, 4) AS avg_fill_price,
       ROUND(gross_amount_usd, 0) AS gross_amount_usd, broker_name, status
FROM SEMANTIC.TRADES
WHERE fund_ticker = %(fund_ticker)s AND trade_date >= DATEADD(day, -%(days)s, CURRENT_DATE())
ORDER BY trade_date DESC LIMIT %(limit)s"""
        return sql, self.model_dump()


METRICS: dict[str, type[BaseModel]] = {
    "exposure": Exposure,
    "exposure_history": ExposureHistory,
    "compliance": Compliance,
    "fund_nav": FundNav,
    "recent_trades": RecentTrades,
}


def catalogue_for_prompt() -> str:
    lines = []
    for name, model in METRICS.items():
        props = model.model_json_schema()["properties"]
        args = ", ".join(f"{k}: {v.get('enum') or v.get('type') or v.get('anyOf')}" for k, v in props.items())
        lines.append(f"- {name}: {model.__doc__.strip()} Args: {args}")
    return "\n".join(lines)


def compile_call(metric: str, args: dict) -> tuple[str, dict]:
    if metric not in METRICS:
        raise ValueError(f"unknown metric {metric!r}; choose one of {list(METRICS)}")
    return METRICS[metric](**args).compile()
