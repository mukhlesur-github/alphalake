"""`alphalake generate`: write all synthetic batch + history files under data/landing/ (mirrors S3)."""

import json
import time

import numpy as np
import pandas as pd

from alphalake.common.config import get_settings
from alphalake.generators.market import simulate_fx, simulate_prices
from alphalake.generators.portfolio import simulate_portfolios
from alphalake.generators.universe import build_universe, snapshot

START, END = "2024-01-01", "2026-10-30"


def generate() -> None:
    t0 = time.time()
    s = get_settings()
    rng = np.random.default_rng(s.seed)
    out = s.data_dir / "landing"
    state = s.data_dir / "state"
    days = pd.bdate_range(START, END)
    month_ends = pd.DatetimeIndex(pd.Series(days).groupby([days.year, days.month]).max().to_numpy())

    uni = build_universe(rng, month_ends)
    prices = simulate_prices(rng, uni.securities, days)
    fx = simulate_fx(rng, days)
    events, holdings = simulate_portfolios(rng, uni, prices, fx, month_ends)

    def write(df: pd.DataFrame, rel: str):
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if rel.endswith(".csv"):
            df.to_csv(p, index=False)
        else:
            df.to_parquet(p, index=False)

    sec_cols = ["security_id", "ticker", "isin", "name", "asset_class", "gics_sector", "gics_sub_industry",
                "country", "currency", "credit_rating", "esg_score", "coupon", "maturity_date", "as_of_date"]
    fund_cols = ["fund_id", "fund_ticker", "fund_name", "strategy", "region", "expense_ratio", "inception_date",
                 "manager_name", "manager_email", "as_of_date"]
    for i, me in enumerate(month_ends):
        snap = snapshot(uni.securities, uni.changes, "security_id", me)[sec_cols]
        if i % 9 == 4:  # chaos: a row with an invalid ISIN check digit
            bad = snap.iloc[[0]].copy()
            bad["security_id"], bad["isin"] = "SEC-99999", "US00000000X9"
            snap = pd.concat([snap, bad])
        write(snap, f"batch/securities/securities_{me.date()}.csv")
        write(snapshot(uni.funds, uni.fund_changes, "fund_ticker", me)[fund_cols], f"batch/funds/funds_{me.date()}.csv")
        write(holdings[holdings.as_of_date == me.date()], f"batch/holdings/holdings_{me.date()}.parquet")

    prices = prices[rng.random(len(prices)) > 0.002]  # chaos: missing prices -> forward-fill in Silver
    for (y, m), g in prices.groupby([prices.price_date.dt.year, prices.price_date.dt.month]):
        write(g.assign(price_date=g.price_date.dt.date), f"batch/prices/prices_{y}-{m:02d}.parquet")
    for (y, m), g in fx.groupby([fx.rate_date.dt.year, fx.rate_date.dt.month]):
        write(g.assign(rate_date=g.rate_date.dt.date), f"batch/fx/fx_{y}-{m:02d}.parquet")
    write(uni.limits, "batch/fund_limits/fund_limits.csv")
    write(uni.clients.assign(as_of_date=month_ends[-1].date()), "batch/clients/clients.csv")

    by_month: dict[str, list[dict]] = {}
    for e in events:
        by_month.setdefault(e["trade"]["trade_date"][:7], []).append(e)
    for month, rows in by_month.items():
        p = out / f"trades/history/trades_{month}.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    # State the live stream producer continues from
    state.mkdir(parents=True, exist_ok=True)
    final_sec = snapshot(uni.securities, uni.changes, "security_id", month_ends[-1])
    final_sec.drop(columns="as_of_date").to_parquet(state / "securities.parquet", index=False)
    last = prices[prices.price_date == prices.price_date.max()][["security_id", "close"]]
    last.to_parquet(state / "last_prices.parquet", index=False)
    (state / "fund_members.json").write_text(json.dumps(uni.fund_members))
    (state / "funds.json").write_text(uni.funds.drop(columns="initial_aum_usd").to_json(orient="records"))

    print(f"securities={len(uni.securities)} funds={len(uni.funds)} prices={len(prices):,} "
          f"trade_events={len(events):,} holdings={len(holdings):,} months={len(month_ends)} "
          f"in {time.time() - t0:.1f}s -> {out}")
