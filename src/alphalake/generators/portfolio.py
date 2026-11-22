"""Target weights -> month-end quantities -> trades (lifecycle events) + custodian holdings."""

import zlib

import numpy as np
import pandas as pd

from alphalake.generators.events import lifecycle, to_json_lines


def target_weights(rng, fund: str, members: list[str], month_idx: int, n_months: int) -> np.ndarray:
    n = len(members)
    if fund != "GTIF":
        base = np.random.default_rng(zlib.crc32(fund.encode())).dirichlet(np.full(n, 3.0))
        w = base * np.exp(rng.normal(0, 0.05, n))
        return w / w.sum()
    # GTIF: members[0:8] semis, [8:12] equipment ([8] is the big one that gets reclassified), rest other IT.
    t = month_idx / max(1, n_months - 1)
    semis_total = 0.26 + 0.05 * t
    equip = np.array([0.055, 0.02, 0.015, 0.01])
    other_total = 1 - semis_total - equip.sum()
    semis = np.random.default_rng(7).dirichlet(np.full(8, 4.0)) * semis_total
    other = np.random.default_rng(8).dirichlet(np.full(n - 12, 3.0)) * other_total
    w = np.r_[semis, equip, other] * np.exp(rng.normal(0, 0.02, n))
    return w / w.sum()


def simulate_portfolios(rng, uni, prices: pd.DataFrame, fx: pd.DataFrame, month_ends: pd.DatetimeIndex):
    """Returns (trade_event_rows, custodian_holdings_df)."""
    px = prices.pivot(index="price_date", columns="security_id", values="close")
    fxp = fx.pivot(index="rate_date", columns="currency", values="usd_per_unit")
    sec = uni.securities.set_index("security_id")
    ccy = sec.currency
    days = px.index
    events, holdings, tid = [], [], 0
    aum = dict(zip(uni.funds.fund_ticker, uni.funds.initial_aum_usd))

    for fund, members in uni.fund_members.items():
        q = pd.Series(0.0, index=members)
        for m, me in enumerate(month_ends):
            month_days = days[(days.month == me.month) & (days.year == me.year)]
            usd_px = px.loc[me, members] * fxp.loc[me, ccy[members]].to_numpy()
            aum[fund] *= float(np.exp(rng.normal(0.006, 0.025)))
            w = target_weights(rng, fund, members, m, len(month_ends))
            target = np.floor(aum[fund] * w / usd_px.to_numpy())
            for sid, tgt in zip(members, target):
                diff = tgt - q[sid]
                if q[sid] > 0 and abs(diff) < 0.02 * q[sid]:
                    continue  # don't churn tiny rebalances
                if diff == 0:
                    continue
                tid += 1
                d = month_days[int(rng.integers(0, max(1, len(month_days) - 3)))]
                s = sec.loc[sid]
                cancel = rng.random() < 0.01
                evs = lifecycle(
                    rng, trade_id=f"T-{d:%Y%m%d}-{tid:06d}", fund_id=fund,
                    sec={"security_id": sid, "ticker": s["ticker"], "isin": s["isin"], "currency": ccy[sid]},
                    side="BUY" if diff > 0 else "SELL", qty=float(abs(diff)), price=float(px.loc[d, sid]),
                    trade_date=d.date(), cancel=cancel, correct=rng.random() < 0.01,
                )
                events.extend(to_json_lines(evs))
                if cancel:  # cancelled -> rebook as a fresh trade so holdings still hit target
                    tid += 1
                    evs = lifecycle(rng, trade_id=f"T-{d:%Y%m%d}-{tid:06d}", fund_id=fund,
                                    sec={"security_id": sid, "ticker": s["ticker"], "isin": s["isin"], "currency": ccy[sid]},
                                    side="BUY" if diff > 0 else "SELL", qty=float(abs(diff)),
                                    price=float(px.loc[d, sid]), trade_date=d.date())
                    events.extend(to_json_lines(evs))
                q[sid] = tgt
            h = pd.DataFrame({"as_of_date": me.date(), "fund_id": fund, "security_id": members,
                              "quantity": q.to_numpy(), "currency": ccy[members].to_numpy(),
                              "custodian": "Fictional Trust Co"})
            h["market_value_local"] = (h.quantity * px.loc[me, members].to_numpy()).round(2)
            holdings.append(h[h.quantity > 0])

    hold = pd.concat(holdings, ignore_index=True)
    # Custodian recon breaks: a few quantities off, a few rows missing
    breaks = rng.random(len(hold)) < 0.004
    hold.loc[breaks, "quantity"] = (hold.loc[breaks, "quantity"] * rng.uniform(0.9, 1.1, breaks.sum())).round()
    hold = hold[rng.random(len(hold)) > 0.001].reset_index(drop=True)
    return events, hold
