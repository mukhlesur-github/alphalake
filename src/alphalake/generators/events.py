"""Trade-event data contract (Pydantic) + lifecycle builder + chaos injection."""

import copy
import uuid
from datetime import date, datetime, timedelta
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

EventType = Literal["NEW", "PARTIALLY_FILLED", "FILLED", "CORRECTED", "CANCELLED", "SETTLED"]
BROKERS = [("BRK-01", "Fictional Securities LLC"), ("BRK-02", "Harbor Prime Brokerage"),
           ("BRK-03", "Atlas Capital Markets"), ("BRK-04", "Meridian Execution")]
VENUES = ["XNAS", "XNYS", "ARCX", "BATS", "XLON", "XETR"]


class SecurityRef(BaseModel):
    security_id: str
    ticker: str
    isin: str


class Broker(BaseModel):
    broker_id: str
    name: str


class Trade(BaseModel):
    trade_id: str
    fund_id: str
    security: SecurityRef
    side: Literal["BUY", "SELL"]
    order_qty: float = Field(gt=0)
    limit_price: float = Field(gt=0)
    currency: str
    broker: Broker
    trader_id: str
    trade_date: date


class Fill(BaseModel):
    fill_id: str
    qty: float = Field(gt=0)
    price: float = Field(gt=0)
    venue: str
    ts: datetime


class Fees(BaseModel):
    commission: float
    sec_fee: float | None = None  # added in schema 1.1


class Settlement(BaseModel):
    settle_date: date
    custodian: str = "Fictional Trust Co"


class TradeEvent(BaseModel):
    event_id: str
    event_type: EventType
    event_seq: int
    event_ts: datetime
    trade: Trade
    fills: list[Fill] = []  # cumulative fills so far: the latest event carries full state
    fees: Fees
    settlement: Settlement
    schema_version: Literal["1.0", "1.1"] = "1.1"


def lifecycle(rng: np.random.Generator, *, trade_id: str, fund_id: str, sec: dict, side: str, qty: float,
              price: float, trade_date: date, cancel: bool = False, correct: bool = False) -> list[TradeEvent]:
    """NEW -> PARTIALLY_FILLED* -> FILLED -> (CORRECTED) -> SETTLED, or NEW -> CANCELLED."""
    broker = BROKERS[int(rng.integers(len(BROKERS)))]
    ts = datetime(trade_date.year, trade_date.month, trade_date.day, 14, 30) + timedelta(
        minutes=int(rng.integers(0, 360)))
    trade = Trade(trade_id=trade_id, fund_id=fund_id, side=side, order_qty=qty,
                  limit_price=round(price * (1.01 if side == "BUY" else 0.99), 4),
                  security=SecurityRef(**sec), currency=sec_currency(sec), trader_id=f"TR-{int(rng.integers(1, 12)):02d}",
                  broker=Broker(broker_id=broker[0], name=broker[1]), trade_date=trade_date)
    fees = Fees(commission=round(qty * price * 0.0004, 2), sec_fee=round(qty * price * 0.0000278, 2))
    settle = Settlement(settle_date=trade_date + timedelta(days=2))
    events: list[TradeEvent] = []

    def emit(kind, fills, at):
        events.append(TradeEvent(event_id=str(uuid.UUID(int=int(rng.integers(2**63)) << 64 | len(events))),
                                 event_type=kind, event_seq=len(events) + 1, event_ts=at, trade=trade,
                                 fills=copy.deepcopy(fills), fees=fees, settlement=settle))

    emit("NEW", [], ts)
    if cancel:
        emit("CANCELLED", [], ts + timedelta(minutes=3))
        return events
    n_fills = int(rng.integers(1, 4))
    splits = np.diff(np.round(np.sort(np.r_[0, rng.uniform(0, 1, n_fills - 1), 1]) * qty))
    fills: list[Fill] = []
    for i, q in enumerate(splits):
        ts = ts + timedelta(seconds=int(rng.integers(5, 600)))
        fills.append(Fill(fill_id=f"F{i + 1}", qty=float(max(q, 1)), venue=VENUES[int(rng.integers(len(VENUES)))],
                          price=round(price * (1 + rng.normal(0, 0.0015)), 4), ts=ts))
        emit("FILLED" if i == n_fills - 1 else "PARTIALLY_FILLED", fills, ts)
    fills[-1].qty += qty - sum(f.qty for f in fills)  # rounding: total filled == order qty
    events[-1].fills = copy.deepcopy(fills)
    if correct:  # broker busts and rebooks the last fill at a different price
        fills[-1].price = round(fills[-1].price * 1.004, 4)
        emit("CORRECTED", fills, ts + timedelta(hours=1))
    emit("SETTLED", fills, datetime.combine(settle.settle_date, datetime.min.time()) + timedelta(hours=12))
    return events


def sec_currency(sec: dict) -> str:
    return sec.get("currency", "USD")


def to_json_lines(events: list[TradeEvent]) -> list[dict]:
    return [e.model_dump(mode="json") for e in events]


def inject_chaos(rng: np.random.Generator, rows: list[dict], *, dup=0.03, shuffle=0.05, malformed=0.01,
                 v10=0.1) -> list[dict]:
    """At-least-once delivery, out-of-order, malformed payloads and schema drift."""
    out = []
    for r in rows:
        r = copy.deepcopy(r)
        if rng.random() < v10:
            r["schema_version"] = "1.0"
            r["fees"].pop("sec_fee", None)
        if rng.random() < malformed:
            bad = copy.deepcopy(r)
            bad["event_id"] = str(uuid.uuid4())
            if rng.random() < 0.5:
                bad["trade"].pop("trade_id")
            else:
                bad["trade"]["order_qty"] = "twenty"
            out.append(bad)
        out.append(r)
        if rng.random() < dup:
            out.append(copy.deepcopy(r))
    for i in range(len(out) - 1):  # swap neighbours -> out-of-order arrival
        if rng.random() < shuffle:
            out[i], out[i + 1] = out[i + 1], out[i]
    return out
