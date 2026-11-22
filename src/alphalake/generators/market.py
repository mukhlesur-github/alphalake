"""Daily prices (sector-correlated GBM) and FX rates."""

import numpy as np
import pandas as pd


def simulate_prices(rng: np.random.Generator, sec: pd.DataFrame, days: pd.DatetimeIndex) -> pd.DataFrame:
    n_days, n_sec = len(days), len(sec)
    dt = 1 / 252
    market = rng.normal(0.08 * dt, 0.16 * np.sqrt(dt), n_days)
    sectors = sec.gics_sector.unique()
    sector_f = {s: rng.normal(0, 0.12 * np.sqrt(dt), n_days) for s in sectors}
    is_bond = (sec.asset_class == "BOND").to_numpy()
    is_bill = (sec.gics_sub_industry == "Treasury Bill").to_numpy()

    beta = np.where(is_bond, 0.05, rng.uniform(0.7, 1.4, n_sec))
    drift = np.where(is_bond, 0.0, rng.normal(0.04, 0.06, n_sec)) * dt
    # Semis get a tailwind so GTIF's semiconductor weight drifts up between rebalances
    drift = drift + np.where(sec.gics_sub_industry.str.startswith("Semiconductor").to_numpy(), 0.15 * dt, 0)
    idio_vol = np.where(is_bill, 0.002, np.where(is_bond, 0.04, rng.uniform(0.15, 0.35, n_sec)))
    sec_load = np.where(is_bond, 0.1, 1.0)

    rets = (
        drift[None, :]
        + beta[None, :] * market[:, None]
        + sec_load[None, :] * np.column_stack([sector_f[s] for s in sec.gics_sector])
        + rng.normal(0, 1, (n_days, n_sec)) * idio_vol[None, :] * np.sqrt(dt)
    )
    start = np.where(is_bond, rng.uniform(92, 105, n_sec), rng.lognormal(4.3, 0.8, n_sec))
    start = np.where(is_bill, 99.5, start)
    close = start[None, :] * np.exp(np.cumsum(rets, axis=0))

    df = pd.DataFrame(close, index=days, columns=sec.security_id).stack().rename("close").reset_index()
    df.columns = ["price_date", "security_id", "close"]
    df["close"] = df.close.round(4)
    df["volume"] = rng.integers(10_000, 5_000_000, len(df))
    return df


def simulate_fx(rng: np.random.Generator, days: pd.DatetimeIndex) -> pd.DataFrame:
    out = []
    for ccy, start, vol in [("EUR", 1.09, 0.07), ("GBP", 1.27, 0.08), ("JPY", 0.0068, 0.10)]:
        path = start * np.exp(np.cumsum(rng.normal(0, vol / np.sqrt(252), len(days))))
        out.append(pd.DataFrame({"rate_date": days, "currency": ccy, "usd_per_unit": path.round(6)}))
    out.append(pd.DataFrame({"rate_date": days, "currency": "USD", "usd_per_unit": 1.0}))
    return pd.concat(out, ignore_index=True)
