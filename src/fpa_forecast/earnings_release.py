"""Headcount from Alphabet's quarterly earnings releases (8-K Item 2.02, exhibit 99.1).

Headcount is not XBRL-tagged in the 10-Q/10-K instances. The earnings release's supplemental
table reports "Number of employees" at quarter end for the current quarter and the same quarter
a year earlier. Each value is stored with its 8-K accession and exhibit URL.
"""
from __future__ import annotations

import html
import re

import pandas as pd

from .paths import INTERIM_DIR, RAW_DIR
from .sec_fetch import ARCHIVE_URL, CIK, SUBMISSIONS_PAGE_URL, SUBMISSIONS_URL, _cached_json, _Client

EXHIBIT_RE = re.compile(r"(ex-?99|exhibit-?99)", re.I)


def earnings_8ks(client: _Client, filed_from: str = "2017-04-01") -> list[dict]:
    main = _cached_json(client, SUBMISSIONS_URL.format(cik=CIK), RAW_DIR / "submissions" / "main.json")
    blocks = [main["filings"]["recent"]] + [
        _cached_json(client, SUBMISSIONS_PAGE_URL.format(name=p["name"]), RAW_DIR / "submissions" / p["name"])
        for p in main["filings"].get("files", [])]
    out = {}
    for b in blocks:
        for form, filed, acc, items in zip(b["form"], b["filingDate"], b["accessionNumber"], b["items"]):
            if form == "8-K" and "2.02" in (items or "") and filed >= filed_from:
                out[acc] = {"accession": acc, "filed": filed}
    return sorted(out.values(), key=lambda r: r["filed"])


def _text(raw: str) -> str:
    t = re.sub(r"<[^>]+>", " ", raw)
    t = html.unescape(html.unescape(t)).replace("\xa0", " ")
    return re.sub(r"\s+", " ", t)


def fetch_exhibits(client: _Client | None = None) -> list[dict]:
    client = client or _Client()
    out = []
    for f in earnings_8ks(client):
        nodash = f["accession"].replace("-", "")
        folder = RAW_DIR / "8k" / nodash
        idx = _cached_json(client, ARCHIVE_URL.format(cik=CIK, acc_nodash=nodash, name="index.json"), folder / "index.json")
        names = [i["name"] for i in idx["directory"]["item"] if i["name"].lower().endswith(".htm")]
        for n in [n for n in names if EXHIBIT_RE.search(n)]:
            path = folder / n
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(client.get(ARCHIVE_URL.format(cik=CIK, acc_nodash=nodash, name=n)).text)
            out.append({**f, "exhibit": n, "path": path,
                        "url": ARCHIVE_URL.format(cik=CIK, acc_nodash=nodash, name=n)})
    return out


QEND = r"(March 31|June 30|September 30|December 31)"
DATE_RE = re.compile(QEND + r",?\s*(20\d\d)(?:\s+(?:and\s+)?(20\d\d))?")
QNUM = {"March 31": 1, "June 30": 2, "September 30": 3, "December 31": 4}


def parse_headcount(text: str, filed: str | None = None) -> list[tuple[str, int]]:
    """Return [(fiscal_quarter, employees)] from the release's employee-count row.

    Releases print 'Number of employees <prior-year value> <current value>' below a column header in
    one of three forms: 'Quarter Ended September 30, 2025 2026', 'Three Months Ended September 30, 2018
    Three Months Ended September 30, 2019', or 'quarters ended December 31, 2016 and 2017'. The header
    nearest above the row gives the quarter and the two years (older first, as printed).
    """
    m = re.search(r"Number of employees\s*(?:\(\d\)\s*)?([\d,]{5,9})\s+([\d,]{5,9})", text)
    if not m:
        return []
    vals = [int(v.replace(",", "")) for v in m.groups()]
    hdrs = list(DATE_RE.finditer(text[max(0, m.start() - 6000): m.start()]))
    if not hdrs:
        return []
    last = hdrs[-1]
    month = last.group(1)
    if last.group(3):
        y1, y2 = int(last.group(2)), int(last.group(3))
    else:
        same = [h for h in hdrs if h.group(1) == month]
        if len(same) < 2:
            return []
        y1, y2 = int(same[-2].group(2)), int(same[-1].group(2))
    if y2 != y1 + 1:
        return []
    q = QNUM[month]
    if filed is not None:  # the current column must be the last quarter that ended before the filing
        cur = pd.Period(filed, freq="Q") - 1
        if (cur.year, cur.quarter) != (y2, q):
            return []
    return [(f"{y1}Q{q}", vals[0]), (f"{y2}Q{q}", vals[1])]


def headcount_table(client: _Client | None = None) -> pd.DataFrame:
    rows = []
    for ex in fetch_exhibits(client):
        for fq, n in parse_headcount(_text(ex["path"].read_text()), ex["filed"]):
            rows.append({"fiscal_quarter": fq, "employees": n, "accession": ex["accession"], "filed": ex["filed"],
                         "source_url": ex["url"]})
    df = pd.DataFrame(rows).sort_values(["fiscal_quarter", "filed"])
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(INTERIM_DIR / "headcount_vintages.csv", index=False)
    return df
