"""Build the quarterly Alphabet dataset from parsed XBRL facts.

Steps
1. Parse every cached 10-Q / 10-K instance into one long fact table.
2. Map tagged facts to canonical line items (revenue by type, segment revenue,
   cost lines, operating income, segment operating income, capex).
3. For each (line, period) keep every filing that reported it ("vintages").
   The latest vintage is the value we use; if it differs from the first
   report by more than $1M the period is flagged as restated.
4. Turn reported durations into fiscal quarters:
   - 3-month facts are used as is;
   - Q4 is not in any 10-Q, so Q4 = fiscal year (10-K) - nine months (Q3 10-Q);
   - cash-flow items (capex) are year-to-date, so quarters are differenced.

All values are USD millions. Every row keeps the accession numbers it came from.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from .paths import INTERIM_DIR, PROCESSED_DIR, RAW_DIR
from .xbrl_parse import parse_instance

RESTATEMENT_TOL_M = 1.0  # $1M
EDGAR_INDEX = "https://www.sec.gov/Archives/edgar/data/1652044/{nodash}/{acc}-index.htm"

# Revenue-by-type disclosure (Search, YouTube, Network, Cloud split out) starts
# with the FY2019 10-K filed 2020-02-04. Earlier "Google other revenues"
# included Cloud, so older values for these members use a different definition.
NEW_REVENUE_DISCLOSURE = "2020-02-04"
# Google Services / Google Cloud became reportable segments in the FY2020 10-K.
SEGMENTS_FROM = "2021-02-03"

REVENUE_CONCEPTS = {
    "us-gaap:Revenues",
    "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
    "us-gaap:AdvertisingRevenue",
}

MEMBER_ALIASES = {
    "GoogleServicesSegmentMember": "GoogleServicesMember",
    "GoogleCloudSegmentMember": "GoogleCloudMember",
    "GoogleNetworkMembersPropertiesMember": "GoogleNetworkMember",
    "SubscriptionsPlatformsAndDevicesRevenueMember": "OtherRevenuesMember",
}


def _dims_dict(dims: str) -> dict[str, str]:
    out = {}
    if not dims:
        return out
    for part in dims.split("|"):
        axis, member = part.split("=")
        axis = axis.split(":")[-1]
        member = member.split(":")[-1]
        out[axis] = MEMBER_ALIASES.get(member, member)
    return out


@dataclass(frozen=True)
class LineRule:
    line: str
    concepts: frozenset[str]
    match: Callable[[dict[str, str]], bool]
    filed_from: str = "1900-01-01"
    flow: str = "income"  # "income" (discrete quarters) or "ytd" (cash flow)


def _only(**want: str) -> Callable[[dict[str, str]], bool]:
    def f(d: dict[str, str]) -> bool:
        return d == want
    return f


def _product(member: str) -> Callable[[dict[str, str]], bool]:
    def f(d: dict[str, str]) -> bool:
        return d.get("ProductOrServiceAxis") == member and set(d) <= {"ProductOrServiceAxis", "StatementBusinessSegmentsAxis"}
    return f


def _cloud(d: dict[str, str]) -> bool:
    return _product("GoogleCloudMember")(d) or d == {"StatementBusinessSegmentsAxis": "GoogleCloudMember"}


def _seg_oi(member: str) -> Callable[[dict[str, str]], bool]:
    def f(d: dict[str, str]) -> bool:
        return d == {"ConsolidationItemsAxis": "OperatingSegmentsMember", "StatementBusinessSegmentsAxis": member}
    return f


REV = frozenset(REVENUE_CONCEPTS)
RULES: list[LineRule] = [
    LineRule("total_revenue", frozenset({"us-gaap:Revenues", "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"}), _only()),
    LineRule("search_other", REV, _product("GoogleSearchOtherMember"), NEW_REVENUE_DISCLOSURE),
    LineRule("youtube_ads", REV, _product("YouTubeAdvertisingRevenueMember"), NEW_REVENUE_DISCLOSURE),
    LineRule("google_network", REV, _product("GoogleNetworkMember"), NEW_REVENUE_DISCLOSURE),
    LineRule("subscriptions_platforms_devices", REV, _product("OtherRevenuesMember"), NEW_REVENUE_DISCLOSURE),
    LineRule("google_cloud", REV, _cloud, NEW_REVENUE_DISCLOSURE),
    LineRule("google_services_revenue", REV, _only(StatementBusinessSegmentsAxis="GoogleServicesMember"), SEGMENTS_FROM),
    LineRule("other_bets_revenue", REV, _only(StatementBusinessSegmentsAxis="AllOtherSegmentsMember")),
    LineRule("hedging_gains_losses", frozenset({"us-gaap:RevenueNotFromContractWithCustomer"}), _only()),
    LineRule("cost_of_revenues", frozenset({"us-gaap:CostOfRevenue"}), _only()),
    LineRule("research_development", frozenset({"us-gaap:ResearchAndDevelopmentExpense"}), _only()),
    LineRule("sales_marketing", frozenset({"us-gaap:SellingAndMarketingExpense"}), _only()),
    LineRule("general_administrative", frozenset({"us-gaap:GeneralAndAdministrativeExpense"}), _only()),
    LineRule("total_costs_expenses", frozenset({"us-gaap:CostsAndExpenses"}), _only()),
    LineRule("operating_income", frozenset({"us-gaap:OperatingIncomeLoss"}), _only()),
    LineRule("oi_google_services", frozenset({"us-gaap:OperatingIncomeLoss"}), _seg_oi("GoogleServicesMember"), SEGMENTS_FROM),
    LineRule("oi_google_cloud", frozenset({"us-gaap:OperatingIncomeLoss"}), _seg_oi("GoogleCloudMember"), SEGMENTS_FROM),
    LineRule("oi_other_bets", frozenset({"us-gaap:OperatingIncomeLoss"}), _seg_oi("AllOtherSegmentsMember"), SEGMENTS_FROM),
    LineRule("oi_alphabet_level", frozenset({"us-gaap:OperatingIncomeLoss"}), _only(ConsolidationItemsAxis="CorporateNonSegmentMember"), SEGMENTS_FROM),
    LineRule("capex", frozenset({"us-gaap:PaymentsToAcquirePropertyPlantAndEquipment"}), _only(), flow="ytd"),
]

REVENUE_LINES = ["search_other", "youtube_ads", "google_network", "subscriptions_platforms_devices",
                 "google_cloud", "other_bets_revenue", "hedging_gains_losses"]
SERVICES_LINES = ["search_other", "youtube_ads", "google_network", "subscriptions_platforms_devices"]
COST_LINES = ["cost_of_revenues", "research_development", "sales_marketing", "general_administrative"]


# --------------------------------------------------------------------------- facts
def load_facts(use_cache: bool = True) -> pd.DataFrame:
    """All numeric facts from every cached filing, plus filing metadata."""
    frames = []
    for meta_path in sorted(RAW_DIR.glob("*/filing.json")):
        meta = json.loads(meta_path.read_text())
        df = parse_instance(meta_path.parent / meta["instance"])
        if df.empty:
            continue
        for k in ("accession", "form", "filed", "report_date"):
            df[k] = meta[k]
        frames.append(df)
    if not frames:
        raise FileNotFoundError("No cached filings under data/raw. Run `python run_pipeline.py --fetch` first.")
    return pd.concat(frames, ignore_index=True)


def map_facts(facts: pd.DataFrame) -> pd.DataFrame:
    """Keep only facts that match a line rule; one row per (line, period, filing)."""
    facts = facts[~facts["instant"] & ~facts["typed_dims"] & (facts["unit"].str.upper() == "USD")].copy()
    facts["dd"] = facts["dims"].map(_dims_dict)
    out = []
    for rule in RULES:
        sub = facts[facts["concept"].isin(rule.concepts) & (facts["filed"] >= rule.filed_from)]
        sub = sub[sub["dd"].map(rule.match)]
        if sub.empty:
            continue
        sub = sub.assign(line=rule.line, flow=rule.flow)
        out.append(sub)
    m = pd.concat(out, ignore_index=True)
    m["value_m"] = m["value"] / 1e6
    # One value per (line, period, filing). Prefer us-gaap:Revenues over the
    # contract-revenue tag when a filing carries both for the same total.
    pref = {"us-gaap:Revenues": 0, "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax": 1}
    m["pref"] = m["concept"].map(pref).fillna(2)
    m = m.sort_values(["line", "start", "end", "accession", "pref"])
    m = m.drop_duplicates(["line", "start", "end", "accession"], keep="first")
    m["days"] = (pd.to_datetime(m["end"]) - pd.to_datetime(m["start"])).dt.days + 1
    m["span"] = pd.cut(m["days"], bins=[0, 100, 190, 280, 380], labels=["3M", "6M", "9M", "12M"]).astype(str)
    cols = ["line", "flow", "concept", "dims", "start", "end", "span", "value_m", "accession", "form", "filed", "report_date"]
    return m[cols].reset_index(drop=True)


# ------------------------------------------------------------------- vintages
def vintages(mapped: pd.DataFrame) -> pd.DataFrame:
    """Per (line, start, end): first-reported and latest-reported value."""
    g = mapped.sort_values("filed").groupby(["line", "flow", "start", "end", "span"], as_index=False)
    v = g.agg(first_value=("value_m", "first"), latest_value=("value_m", "last"),
              first_filed=("filed", "first"), latest_filed=("filed", "last"),
              first_accession=("accession", "first"), latest_accession=("accession", "last"),
              n_vintages=("value_m", "size"))
    v["restated"] = (v["latest_value"] - v["first_value"]).abs() > RESTATEMENT_TOL_M
    return v


def restatement_events(mapped: pd.DataFrame) -> pd.DataFrame:
    """Filing dates at which a line's previously reported value changed.

    An event at date d for line L means some period of L was reported with a
    different value in the filing dated d than in the previous filing that
    reported the same period. Values filed on different sides of an event can
    be on different bases and must not be combined.
    """
    rows = []
    for (line, start, end), g in mapped.sort_values("filed").groupby(["line", "start", "end"]):
        vals, dates, accs = g["value_m"].to_numpy(), g["filed"].to_numpy(), g["accession"].to_numpy()
        for i in range(1, len(vals)):
            if abs(vals[i] - vals[i - 1]) > RESTATEMENT_TOL_M:
                rows.append(dict(line=line, filed=dates[i], accession=accs[i], start=start, end=end,
                                 previous_value_m=vals[i - 1], new_value_m=vals[i]))
    return pd.DataFrame(rows, columns=["line", "filed", "accession", "start", "end", "previous_value_m", "new_value_m"])


REGIME_GAP_DAYS = 400


def regime_starts(event_dates: list[str]) -> list[str]:
    """Collapse restatement events into the filing that started each new basis.

    A recast rolls through the comparative columns of the next four filings
    (each 10-Q restates its prior-year quarter, the 10-K restates prior years),
    so events within ~a year of the first one belong to the same basis change.
    """
    starts: list[str] = []
    for d in sorted(set(event_dates)):
        if not starts or (pd.Timestamp(d) - pd.Timestamp(starts[-1])).days > REGIME_GAP_DAYS:
            starts.append(d)
    return starts


def _consistent(f1: str, f2: str, starts: list[str]) -> bool:
    lo, hi = sorted((f1, f2))
    return not any(lo < e <= hi for e in starts)


def _diff_pair(cur: pd.DataFrame, prev: pd.DataFrame, events: list[str]):
    """Value = cur - prev using a pair of filings with no basis change between them.

    Returns (latest, first) pairs: latest uses the most recent consistent basis,
    first the earliest. Each is (value, cur_accession, prev_accession).
    """
    pairs = []
    for c in cur.itertuples():
        for p in prev.itertuples():
            if _consistent(c.filed, p.filed, events):
                pairs.append((max(c.filed, p.filed), c.filed, c.value_m - p.value_m, c.accession, p.accession))
    if not pairs:
        return None, None
    pairs.sort()
    return pairs[-1][2:], pairs[0][2:]


def quarterize(mapped: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Turn reported spans into one value per fiscal quarter per line."""
    m = mapped.copy()
    m["start"] = pd.to_datetime(m["start"])
    m["end"] = pd.to_datetime(m["end"])
    rows = []
    for (line, flow), g in m.groupby(["line", "flow"]):
        ev = regime_starts(list(events.loc[events["line"] == line, "filed"]))
        spans = {k: gg.sort_values("filed") for k, gg in g.groupby(["span", "start", "end"])}
        for y in sorted(set(g["end"].dt.year)):
            y_start = pd.Timestamp(y, 1, 1)
            for q in range(1, 5):
                q_start = pd.Timestamp(y, 3 * (q - 1) + 1, 1)
                q_end = q_start + pd.offsets.QuarterEnd(0)
                rec = None
                three = spans.get(("3M", q_start, q_end))
                if three is not None and (flow == "income" or q == 1):
                    rec = dict(value_m=three["value_m"].iloc[-1], first_value_m=three["value_m"].iloc[0],
                               derivation="reported_3m", n_vintages=len(three),
                               source_accessions=three["accession"].iloc[-1],
                               first_accessions=three["accession"].iloc[0])
                elif q > 1 and (flow == "ytd" or q == 4):
                    names = {2: ("6M", "3M"), 3: ("9M", "6M"), 4: ("12M", "9M")}[q] if flow == "ytd" else ("12M", "9M")
                    prev_end = q_start - pd.Timedelta(days=1)
                    cur = spans.get((names[0], y_start, q_end))
                    prev = spans.get((names[1], y_start, prev_end))
                    if cur is not None and prev is not None:
                        latest, first = _diff_pair(cur, prev, ev)
                        if latest is not None:
                            rec = dict(value_m=latest[0], first_value_m=first[0],
                                       derivation="fy_minus_9m" if q == 4 else "ytd_difference",
                                       n_vintages=min(len(cur), len(prev)),
                                       source_accessions=_src(latest[1], latest[2]),
                                       first_accessions=_src(first[1], first[2]))
                if rec is None:
                    continue
                rec["restated"] = bool(abs(rec["value_m"] - rec["first_value_m"]) > RESTATEMENT_TOL_M)
                rec.update(line=line, fiscal_quarter=f"{y}Q{q}")
                rows.append(rec)
    return pd.DataFrame(rows)


def _src(*accs: str) -> str:
    accs = [a for a in dict.fromkeys(accs) if isinstance(a, str)]
    return ";".join(accs)


# ------------------------------------------------------------- derived lines
def add_derived(q: pd.DataFrame) -> pd.DataFrame:
    """Lines that are identities of tagged lines (documented in methodology)."""
    w = q.pivot(index="fiscal_quarter", columns="line", values="value_m")
    meta = q.set_index(["fiscal_quarter", "line"])
    meta_src: dict = {}
    extra = []

    def add(line, fq, value, derivation, sources):
        extra.append(dict(line=line, fiscal_quarter=fq, value_m=value, first_value_m=np.nan, derivation=derivation,
                          restated=False, n_vintages=0, source_accessions=_src(*sources), first_accessions=""))

    def srcs(fq, lines):
        out = []
        for ln in lines:
            if (fq, ln) in meta.index:
                out += meta.loc[(fq, ln), "source_accessions"].split(";")
        return out

    for fq, r in w.iterrows():
        # Google Services revenue before segment reporting: sum of its four lines.
        if pd.isna(r.get("google_services_revenue")) and r[SERVICES_LINES].notna().all():
            add("google_services_revenue", fq, r[SERVICES_LINES].sum(), "sum_of_service_lines", srcs(fq, SERVICES_LINES))
        # Hedging is tagged separately only in recent filings; otherwise it is the
        # reconciling item between total revenue and the segment revenues.
        if pd.isna(r.get("hedging_gains_losses")):
            svc = r.get("google_services_revenue")
            if pd.isna(svc) and r[SERVICES_LINES].notna().all():
                svc = r[SERVICES_LINES].sum()
            parts = [svc, r.get("google_cloud"), r.get("other_bets_revenue"), r.get("total_revenue")]
            if all(pd.notna(p) for p in parts):
                add("hedging_gains_losses", fq, parts[3] - parts[0] - parts[1] - parts[2], "residual_total_minus_segments",
                    srcs(fq, ["total_revenue", "google_cloud", "other_bets_revenue", "google_services_revenue"]))
        # European Commission fines were a separate expense line in 2017-2019.
        if r[COST_LINES].notna().all() and pd.notna(r.get("total_costs_expenses")):
            fines = r["total_costs_expenses"] - r[COST_LINES].sum()
            if abs(fines) > RESTATEMENT_TOL_M:
                add("ec_fines", fq, fines, "residual_total_costs_minus_lines", srcs(fq, COST_LINES + ["total_costs_expenses"]))
    if extra:
        q = pd.concat([q, pd.DataFrame(extra)], ignore_index=True)
    meta_src = q.set_index(["fiscal_quarter", "line"])["source_accessions"].fillna("").to_dict()
    # Forecasting target: operating revenue, i.e. total revenue excluding FX hedging.
    w2 = q.pivot(index="fiscal_quarter", columns="line", values="value_m")
    ex = (w2["total_revenue"] - w2["hedging_gains_losses"]).dropna()
    q = pd.concat([q, pd.DataFrame([dict(line="total_revenue_ex_hedging", fiscal_quarter=fq, value_m=v,
                                         first_value_m=np.nan, derivation="total_minus_hedging", restated=False,
                                         n_vintages=0, source_accessions=";".join(dict.fromkeys(
                                             meta_src.get((fq, "total_revenue"), "").split(";")
                                             + meta_src.get((fq, "hedging_gains_losses"), "").split(";"))).strip(";"),
                                         first_accessions="") for fq, v in ex.items()])], ignore_index=True)
    q["period_end"] = pd.PeriodIndex(q["fiscal_quarter"], freq="Q").end_time.date
    q["period_start"] = pd.PeriodIndex(q["fiscal_quarter"], freq="Q").start_time.date
    return q


def tidy(q: pd.DataFrame, first_quarter: str = "2017Q1") -> pd.DataFrame:
    q = q[q["fiscal_quarter"] >= first_quarter].copy()
    q["value_m"] = q["value_m"].round(3)
    q["first_value_m"] = q["first_value_m"].round(3)

    def urls(s: str) -> str:
        return " ".join(EDGAR_INDEX.format(nodash=a.replace("-", ""), acc=a) for a in s.split(";") if a)

    q["source_urls"] = q["source_accessions"].fillna("").map(urls)
    cols = ["fiscal_quarter", "period_start", "period_end", "line", "value_m", "derivation", "restated",
            "first_value_m", "n_vintages", "source_accessions", "first_accessions", "source_urls"]
    return q[cols].sort_values(["line", "fiscal_quarter"]).reset_index(drop=True)


def build(write: bool = True) -> dict[str, pd.DataFrame]:
    facts = load_facts()
    mapped = map_facts(facts)
    v = vintages(mapped)
    events = restatement_events(mapped)
    q = tidy(add_derived(quarterize(mapped, events)))
    wide = q.pivot(index="fiscal_quarter", columns="line", values="value_m").reset_index()
    if write:
        INTERIM_DIR.mkdir(parents=True, exist_ok=True)
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        mapped.to_csv(INTERIM_DIR / "xbrl_facts_mapped.csv.gz", index=False)
        v.to_csv(INTERIM_DIR / "vintages.csv", index=False)
        events.to_csv(INTERIM_DIR / "restatement_events.csv", index=False)
        q.to_csv(PROCESSED_DIR / "alphabet_quarterly_long.csv", index=False)
        wide.to_csv(PROCESSED_DIR / "alphabet_quarterly_wide.csv", index=False)
    return {"mapped": mapped, "vintages": v, "events": events, "long": q, "wide": wide}
