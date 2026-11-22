"""Reference data: securities (with SCD2-triggering changes), funds, limits, clients."""

import string
from dataclasses import dataclass

import numpy as np
import pandas as pd
from faker import Faker

# (sector, sub_industry) pools. Semiconductors vs equipment matters for the GTIF limit story.
EQUITY_SUBS = {
    "Information Technology": [
        "Semiconductors", "Semiconductor Materials & Equipment", "Application Software",
        "Systems Software", "Technology Hardware", "IT Services",
    ],
    "Communication Services": ["Interactive Media", "Telecom Services"],
    "Consumer Discretionary": ["Internet Retail", "Automobiles"],
    "Health Care": ["Pharmaceuticals", "Biotechnology"],
    "Financials": ["Banks", "Insurance"],
    "Energy": ["Integrated Oil & Gas"],
    "Industrials": ["Aerospace & Defense", "Machinery"],
    "Consumer Staples": ["Beverages", "Packaged Foods", "Tobacco"],
    "Utilities": ["Electric Utilities"],
    "Materials": ["Chemicals"],
    "Real Estate": ["REITs"],
}
COUNTRY_CCY = {"US": "USD", "DE": "EUR", "NL": "EUR", "FR": "EUR", "GB": "GBP", "JP": "JPY",
               "TW": "USD", "KR": "USD", "IN": "USD", "BR": "USD", "CN": "USD"}
EM = ["TW", "KR", "IN", "BR", "CN"]
EUROPE = ["DE", "NL", "FR", "GB"]
RATINGS = ["AAA", "AA", "A", "BBB", "BB", "B"]


def isin_check_digit(body: str) -> str:
    """ISO 6166 check digit for the first 11 characters."""
    digits = "".join(str(int(c, 36)) for c in body)
    total = 0
    for i, d in enumerate(reversed(digits)):
        n = int(d) * (2 if i % 2 == 0 else 1)
        total += n // 10 + n % 10
    return str((10 - total % 10) % 10)


def make_isin(country: str, n: int) -> str:
    body = f"{country}{n:09d}"
    return body + isin_check_digit(body)


@dataclass
class Universe:
    securities: pd.DataFrame          # current attributes at start
    changes: pd.DataFrame             # security_id, effective_date, column, new_value
    funds: pd.DataFrame
    fund_changes: pd.DataFrame
    limits: pd.DataFrame
    fund_members: dict[str, list[str]]
    clients: pd.DataFrame


def _tickers(rng, n):
    seen, out = set(), []
    while len(out) < n:
        t = "".join(rng.choice(list(string.ascii_uppercase), rng.integers(3, 5)))
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def build_universe(rng: np.random.Generator, month_ends: pd.DatetimeIndex) -> Universe:
    fake = Faker()
    Faker.seed(int(rng.integers(1e9)))
    rows = []
    sid = 0

    def add_equity(sector, sub, country):
        nonlocal sid
        sid += 1
        rows.append(dict(
            security_id=f"SEC-{sid:05d}", isin=make_isin(country, 100000 + sid),
            name=fake.unique.company(), asset_class="EQUITY", gics_sector=sector, gics_sub_industry=sub,
            country=country, currency=COUNTRY_CCY[country], credit_rating=None,
            esg_score=int(rng.integers(20, 95)), coupon=None, maturity_date=None,
        ))

    def add_bond(kind, rating, country="US"):
        nonlocal sid
        sid += 1
        rows.append(dict(
            security_id=f"SEC-{sid:05d}", isin=make_isin(country, 100000 + sid),
            name=f"{fake.unique.company()} {rng.uniform(1, 7):.2f}% {int(rng.integers(2027, 2045))}",
            asset_class="BOND", gics_sector="Fixed Income", gics_sub_industry=kind,
            country=country, currency="USD", credit_rating=rating, esg_score=int(rng.integers(30, 90)),
            coupon=round(float(rng.uniform(1, 7)), 2),
            maturity_date=str(pd.Timestamp(int(rng.integers(2027, 2045)), 6, 15).date()),
        ))

    # Tech-heavy global universe (GTIF / EUTF)
    for country in ["US"] * 18 + ["TW", "TW", "KR", "KR", "JP", "JP", "NL"]:
        add_equity("Information Technology", rng.choice(EQUITY_SUBS["Information Technology"]), country)
    for sub in ["Semiconductors"] * 6 + ["Semiconductor Materials & Equipment"] * 4:
        add_equity("Information Technology", sub, rng.choice(["US", "TW", "NL", "KR"]))
    for country in EUROPE * 5:
        add_equity("Information Technology", rng.choice(EQUITY_SUBS["Information Technology"][2:]), country)
    # Broad equities
    for sector, subs in EQUITY_SUBS.items():
        for _ in range(18 if sector != "Information Technology" else 6):
            add_equity(sector, rng.choice(subs), rng.choice(["US"] * 6 + EUROPE + EM + ["JP"]))
    for _ in range(40):
        add_equity(rng.choice(list(EQUITY_SUBS)), "", rng.choice(EM))
        rows[-1]["gics_sub_industry"] = rng.choice(EQUITY_SUBS[rows[-1]["gics_sector"]])
    # Bonds
    for _ in range(30):
        add_bond(rng.choice(["Government", "Investment Grade Corporate"]), rng.choice(RATINGS[:4]))
    for _ in range(30):
        add_bond("High Yield Corporate", rng.choice(RATINGS[3:]))
    for _ in range(25):
        add_bond("Municipal", rng.choice(RATINGS[:3]))
    for _ in range(10):
        add_bond("Treasury Bill", "AAA")
    sec = pd.DataFrame(rows)
    sec["ticker"] = _tickers(rng, len(sec))

    # --- Fund membership --------------------------------------------------------------
    eq = sec[sec.asset_class == "EQUITY"]
    it = eq[eq.gics_sector == "Information Technology"]

    def pick(df, n):
        return list(df.sample(n=min(n, len(df)), random_state=int(rng.integers(1e9))).security_id)

    semis = it[it.gics_sub_industry == "Semiconductors"]
    equip = it[it.gics_sub_industry == "Semiconductor Materials & Equipment"]
    gtif = list(semis.security_id[:8]) + list(equip.security_id[:4]) + pick(
        it[~it.gics_sub_industry.str.startswith("Semiconductor") & ~it.country.isin(EUROPE)], 23)
    us = eq[eq.country == "US"]
    members = {
        "GTIF": gtif,
        "EUTF": pick(it[it.country.isin(EUROPE)], 22),
        "USLG": pick(us[us.gics_sector.isin(["Information Technology", "Communication Services",
                                               "Consumer Discretionary", "Health Care"])], 35),
        "USLV": pick(us[us.gics_sector.isin(["Financials", "Energy", "Industrials", "Consumer Staples",
                                               "Utilities"])], 35),
        "ESGL": pick(eq[eq.esg_score >= 65], 30),
        "EMEQ": pick(eq[eq.country.isin(EM)], 35),
        "DIVI": pick(us[us.gics_sector.isin(["Utilities", "Consumer Staples", "Real Estate", "Financials",
                                               "Energy"])], 25),
        "GBND": list(sec[sec.gics_sub_industry.isin(["Government", "Investment Grade Corporate"])].security_id),
        "HYLD": list(sec[sec.gics_sub_industry == "High Yield Corporate"].security_id),
        "MUNI": list(sec[sec.gics_sub_industry == "Municipal"].security_id),
        "MMKT": list(sec[sec.gics_sub_industry == "Treasury Bill"].security_id),
    }
    members["BAL6"] = members["USLG"][:15] + members["USLV"][:15] + members["GBND"][:15]

    # --- SCD2 change log (applied at month-ends) -------------------------------------
    changes = []
    mids = month_ends[1:]
    for _, s in sec.sample(frac=0.25, random_state=1).iterrows():
        d = mids[int(rng.integers(len(mids)))]
        if s.asset_class == "BOND" and s.gics_sub_industry != "Treasury Bill":
            i = RATINGS.index(s.credit_rating)
            new = RATINGS[min(len(RATINGS) - 1, max(0, i + int(rng.choice([-1, 1]))))]
            changes.append((s.security_id, d, "credit_rating", new))
        else:
            changes.append((s.security_id, d, "esg_score", int(np.clip(s.esg_score + rng.integers(-15, 16), 0, 100))))
    for sid_ in sec[sec.asset_class == "EQUITY"].sample(n=5, random_state=2).security_id:
        changes.append((sid_, mids[int(rng.integers(len(mids)))], "name", fake.unique.company()))
    # Planted story: GTIF's largest equipment holding is reclassified into Semiconductors on 2026-06-30,
    # pushing GTIF over its 35% semiconductor limit. Point-in-time joins must show the jump on that date.
    reclass_date = pd.Timestamp("2026-06-30")
    changes.append((gtif[8], reclass_date, "gics_sub_industry", "Semiconductors"))
    change_df = pd.DataFrame(changes, columns=["security_id", "effective_date", "column", "new_value"])

    # --- Funds ------------------------------------------------------------------------
    funds = pd.DataFrame([
        ("GTIF", "Global Tech Innovation Fund", "Equity - Sector", "Global", 2_400e6, 0.0085),
        ("EUTF", "European Tech Fund", "Equity - Regional Sector", "Europe", 650e6, 0.0090),
        ("USLG", "US Large Cap Growth Fund", "Equity", "US", 3_100e6, 0.0055),
        ("USLV", "US Large Cap Value Fund", "Equity", "US", 2_200e6, 0.0050),
        ("ESGL", "ESG Leaders Fund", "Equity - ESG", "Global", 900e6, 0.0070),
        ("EMEQ", "Emerging Markets Equity Fund", "Equity", "Emerging Markets", 1_100e6, 0.0095),
        ("DIVI", "Dividend Income Fund", "Equity Income", "US", 1_300e6, 0.0060),
        ("GBND", "Global Bond Fund", "Fixed Income", "Global", 1_800e6, 0.0045),
        ("HYLD", "High Yield Bond Fund", "Fixed Income", "US", 700e6, 0.0065),
        ("MUNI", "Municipal Bond Fund", "Fixed Income", "US", 600e6, 0.0040),
        ("BAL6", "Balanced 60/40 Fund", "Multi-Asset", "US", 1_500e6, 0.0060),
        ("MMKT", "Money Market Fund", "Cash", "US", 2_000e6, 0.0015),
    ], columns=["fund_ticker", "fund_name", "strategy", "region", "initial_aum_usd", "expense_ratio"])
    funds["fund_id"] = "FND-" + funds.fund_ticker
    funds["inception_date"] = "2015-01-02"
    managers = [fake.name() for _ in range(14)]
    funds["manager_name"] = managers[:12]
    funds["manager_email"] = [n.lower().replace(" ", ".") + "@northwindcap.example" for n in managers[:12]]
    # dbt snapshot story: GTIF manager change + an expense ratio cut
    fund_changes = pd.DataFrame([
        ("GTIF", pd.Timestamp("2025-06-30"), "manager_name", managers[12]),
        ("GTIF", pd.Timestamp("2025-06-30"), "manager_email",
         managers[12].lower().replace(" ", ".") + "@northwindcap.example"),
        ("USLG", pd.Timestamp("2025-12-31"), "expense_ratio", 0.0049),
    ], columns=["fund_ticker", "effective_date", "column", "new_value"])

    limits = pd.DataFrame([
        ("GTIF", "SUB_INDUSTRY_MAX", "gics_sub_industry", "Semiconductors", None, 35.0),
        ("GTIF", "ISSUER_MAX", "security", "*", None, 8.0),
        ("EUTF", "ISSUER_MAX", "security", "*", None, 8.0),
        ("USLG", "SECTOR_MAX", "gics_sector", "*", None, 40.0),
        ("USLG", "ISSUER_MAX", "security", "*", None, 10.0),
        ("USLV", "ISSUER_MAX", "security", "*", None, 10.0),
        ("EMEQ", "COUNTRY_MAX", "country", "*", None, 30.0),
        ("HYLD", "ISSUER_MAX", "security", "*", None, 3.0),
    ], columns=["fund_ticker", "limit_type", "dimension", "dimension_value", "min_pct", "max_pct"])

    clients = pd.DataFrame([dict(
        client_id=f"CL-{i:05d}", first_name=fake.first_name(), last_name=fake.last_name(),
        email=fake.email(), phone=fake.phone_number(), tax_id=fake.ssn(), country="US",
        state=fake.state_abbr(), segment=rng.choice(["Retail", "Retail", "HNW", "Institutional"]),
        risk_profile=rng.choice(["Conservative", "Balanced", "Growth"]), advisor_name=fake.name(),
        fund_ticker=rng.choice(funds.fund_ticker), units=round(float(rng.lognormal(8, 1.2)), 2),
    ) for i in range(1, 1501)])
    return Universe(sec, change_df, funds, fund_changes, limits, members, clients)


def snapshot(base: pd.DataFrame, changes: pd.DataFrame, key: str, as_of: pd.Timestamp) -> pd.DataFrame:
    """State of `base` as of a date, after applying every change effective on or before it."""
    df = base.copy()
    applied = changes[changes.effective_date <= as_of].sort_values("effective_date")
    for _, c in applied.iterrows():
        df.loc[df[key] == c[key], c["column"]] = c["new_value"]
    df["as_of_date"] = as_of.date()
    return df
