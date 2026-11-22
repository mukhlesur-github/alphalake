"""Live trade producer: Pydantic-validated lifecycle events with chaos, flushed as micro-batch files.

MVP stand-in for Kinesis Firehose: every `flush` seconds a JSONL file lands in
landing/trades/live/, Snowpipe loads it, and the Stream + Task graph merges it into SILVER.TRADES_CURRENT.
"""

import json
import time
from datetime import UTC, date, datetime

import numpy as np
import pandas as pd

from alphalake.common.config import get_settings
from alphalake.generators.events import TradeEvent, inject_chaos, lifecycle


def stream(rate: float, seconds: int, flush: int, local: bool) -> None:
    s = get_settings()
    rng = np.random.default_rng(int(time.time()))
    state = s.data_dir / "state"
    sec = pd.read_parquet(state / "securities.parquet").set_index("security_id")
    px = pd.read_parquet(state / "last_prices.parquet").set_index("security_id").close
    members = json.loads((state / "fund_members.json").read_text())
    latest = sorted((s.data_dir / "landing/batch/holdings").glob("*.parquet"))[-1]
    pos = pd.read_parquet(latest).set_index(["fund_id", "security_id"]).quantity

    s3 = cur = None
    if not local and s.landing_mode == "s3" and s.snowflake_auth != "session":
        from alphalake.producers.upload import s3_client
        s3 = s3_client()
    elif not local:
        from alphalake.common.snowflake import connect_pipeline
        cur = connect_pipeline().cursor()

    today = date.today()
    seq = int(time.time()) % 1_000_000
    end = time.time() + seconds
    total = 0
    while time.time() < end:
        t_batch = time.time()
        rows: list[dict] = []
        for _ in range(max(1, int(rng.poisson(rate * flush)))):
            fund = rng.choice(list(members))
            sid = rng.choice(members[fund])
            held = float(pos.get((fund, sid), 0))
            side = "SELL" if held > 0 and rng.random() < 0.3 else "BUY"
            qty = float(max(1, round(held * rng.uniform(0.005, 0.03)))) if side == "SELL" else float(
                rng.integers(100, 5000))
            seq += 1
            evs = lifecycle(rng, trade_id=f"T-{today:%Y%m%d}-L{seq:06d}", fund_id=fund, side=side, qty=qty,
                            sec={"security_id": sid, "ticker": sec.loc[sid, "ticker"], "isin": sec.loc[sid, "isin"],
                                 "currency": sec.loc[sid, "currency"]},
                            price=float(px[sid] * (1 + rng.normal(0, 0.01))), trade_date=today,
                            cancel=rng.random() < 0.03, correct=rng.random() < 0.05)
            if evs[-1].event_type == "SETTLED" and rng.random() < 0.03:  # trade bust after booking
                last = evs[-1]
                evs.append(TradeEvent(**{**last.model_dump(), "event_id": f"{last.event_id}-bust",
                                         "event_type": "CANCELLED", "event_seq": last.event_seq + 1,
                                         "event_ts": datetime.now(UTC)}))
            rows.extend(e.model_dump(mode="json") for e in evs)
        rows = inject_chaos(rng, rows)
        body = "\n".join(json.dumps(r) for r in rows) + "\n"
        key = f"landing/trades/live/{today}/batch_{datetime.now(UTC):%H%M%S%f}.jsonl"
        if local or cur:
            p = s.data_dir / key
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body)
            if cur:
                from alphalake.producers.upload import put_internal
                put_internal(cur, p, key.removeprefix("landing/"))
        else:
            s3.put_object(Bucket=s.alphalake_bucket, Key=key, Body=body.encode())
        total += len(rows)
        print(f"{key}: {len(rows)} events (total {total})")
        time.sleep(max(0, flush - (time.time() - t_batch)))
