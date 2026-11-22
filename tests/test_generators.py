import json

import numpy as np
import pandas as pd

from alphalake.generators.events import TradeEvent, inject_chaos, lifecycle
from alphalake.generators.universe import isin_check_digit


def test_isin_check_digit_matches_real_isin():
    assert isin_check_digit("US037833100") == "5"  # Apple: US0378331005


def test_reference_integrity_and_snapshots(generated):
    land = generated / "landing" / "batch"
    sec = pd.read_csv(sorted((land / "securities").glob("*.csv"))[-1])
    hold = pd.concat(pd.read_parquet(f) for f in (land / "holdings").glob("*.parquet"))
    assert set(hold.security_id) <= set(sec.security_id)
    assert (hold.quantity > 0).all()
    assert len(list((land / "securities").glob("*.csv"))) == 34


def test_planted_gtif_breach_story(generated):
    land = generated / "landing" / "batch"

    def semis_pct(d):
        h = pd.read_parquet(land / f"holdings/holdings_{d}.parquet")
        s = pd.read_csv(land / f"securities/securities_{d}.csv")
        fx = pd.read_parquet(land / f"fx/fx_{d[:7]}.parquet")
        fx = fx[fx.rate_date.astype(str) == d].set_index("currency").usd_per_unit
        g = h[h.fund_id == "GTIF"].merge(s.drop(columns="currency"), on="security_id")
        g["mv_usd"] = g.market_value_local * g.currency.map(fx)
        return 100 * g[g.gics_sub_industry == "Semiconductors"].mv_usd.sum() / g.mv_usd.sum()

    assert semis_pct("2026-05-29") < 35 < semis_pct("2026-06-30")


def test_trade_history_validates_against_contract(generated):
    f = sorted((generated / "landing" / "trades" / "history").glob("*.jsonl"))[0]
    rows = [json.loads(line) for line in f.read_text().splitlines()]
    for r in rows[:500]:
        TradeEvent(**r)


def test_lifecycle_fills_sum_to_order_qty_and_cancel():
    rng = np.random.default_rng(1)
    sec = {"security_id": "SEC-1", "ticker": "AAA", "isin": "US0000000001", "currency": "USD"}
    evs = lifecycle(rng, trade_id="T1", fund_id="GTIF", sec=sec, side="BUY", qty=1000, price=10,
                    trade_date=pd.Timestamp("2026-01-05").date())
    filled = [e for e in evs if e.event_type == "FILLED"][0]
    assert sum(f.qty for f in filled.fills) == 1000
    assert [e.event_seq for e in evs] == list(range(1, len(evs) + 1))
    cancelled = lifecycle(rng, trade_id="T2", fund_id="GTIF", sec=sec, side="BUY", qty=5, price=10,
                          trade_date=pd.Timestamp("2026-01-05").date(), cancel=True)
    assert [e.event_type for e in cancelled] == ["NEW", "CANCELLED"]


def test_chaos_injects_duplicates_and_malformed():
    rng = np.random.default_rng(3)
    sec = {"security_id": "SEC-1", "ticker": "AAA", "isin": "US0000000001", "currency": "USD"}
    rows = []
    for i in range(200):
        rows += [e.model_dump(mode="json") for e in lifecycle(
            rng, trade_id=f"T{i}", fund_id="GTIF", sec=sec, side="BUY", qty=100, price=10,
            trade_date=pd.Timestamp("2026-01-05").date())]
    out = inject_chaos(rng, rows, dup=0.05, malformed=0.02)
    ids = [r["event_id"] for r in out]
    assert len(ids) > len(set(ids))  # duplicates
    assert any("trade_id" not in r["trade"] or isinstance(r["trade"]["order_qty"], str) for r in out)
