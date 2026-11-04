"""Download Alphabet 10-Q / 10-K XBRL instance documents from SEC EDGAR.

SEC requires a descriptive User-Agent with contact details. Set it in the
environment (or in a local, git-ignored `.env` file):

    SEC_USER_AGENT="Your Name your.email@example.com"

Raw files are cached under data/raw/<accession>/ so each document is fetched
at most once. Requests are throttled well below SEC's 10 requests/second.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from .paths import RAW_DIR, REPO_ROOT

CIK = 1652044  # Alphabet Inc.
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SUBMISSIONS_PAGE_URL = "https://data.sec.gov/submissions/{name}"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{name}"
PERIODIC_FORMS = {"10-Q", "10-K", "10-Q/A", "10-K/A"}
MIN_INTERVAL_S = 0.25


@dataclass(frozen=True)
class Filing:
    accession: str
    form: str
    filed: str
    report_date: str
    primary_document: str

    @property
    def acc_nodash(self) -> str:
        return self.accession.replace("-", "")


def user_agent() -> str:
    ua = os.environ.get("SEC_USER_AGENT")
    if not ua:
        env_file = REPO_ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                m = re.match(r'\s*SEC_USER_AGENT\s*=\s*"?([^"]+)"?\s*$', line)
                if m:
                    ua = m.group(1).strip()
    if not ua or "@" not in ua:
        raise RuntimeError(
            "SEC EDGAR needs a User-Agent with contact info. "
            'Set SEC_USER_AGENT="Your Name your.email@example.com" (env var or .env).'
        )
    return ua


class _Client:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent(), "Accept-Encoding": "gzip, deflate"})
        self._last = 0.0

    def get(self, url: str) -> requests.Response:
        wait = MIN_INTERVAL_S - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        for attempt in range(4):
            r = self.session.get(url, timeout=60)
            self._last = time.monotonic()
            if r.status_code == 200:
                return r
            if r.status_code in (429, 503):
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
        r.raise_for_status()
        return r


def _cached_json(client: _Client, url: str, path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    path.parent.mkdir(parents=True, exist_ok=True)
    data = client.get(url).json()
    path.write_text(json.dumps(data))
    return data


def list_filings(client: _Client | None = None, forms: set[str] = PERIODIC_FORMS,
                 filed_from: str = "2017-01-01") -> list[Filing]:
    client = client or _Client()
    main = _cached_json(client, SUBMISSIONS_URL.format(cik=CIK), RAW_DIR / "submissions" / "main.json")
    blocks = [main["filings"]["recent"]]
    for page in main["filings"].get("files", []):
        blocks.append(_cached_json(client, SUBMISSIONS_PAGE_URL.format(name=page["name"]),
                                   RAW_DIR / "submissions" / page["name"]))
    out: dict[str, Filing] = {}
    for b in blocks:
        for form, filed, acc, doc, rdate in zip(b["form"], b["filingDate"], b["accessionNumber"],
                                                b["primaryDocument"], b["reportDate"]):
            if form in forms and filed >= filed_from:
                out[acc] = Filing(acc, form, filed, rdate, doc)
    return sorted(out.values(), key=lambda f: f.filed)


def _pick_instance(names: list[str]) -> str:
    # Inline XBRL filings (2019+) ship an extracted instance "<doc>_htm.xml";
    # older filings ship a standalone instance "goog-YYYYMMDD.xml".
    htm_xml = [n for n in names if n.endswith("_htm.xml")]
    if htm_xml:
        return htm_xml[0]
    plain = [n for n in names if re.fullmatch(r"goog-\d{8}\.xml", n)]
    if plain:
        return plain[0]
    raise FileNotFoundError(f"no XBRL instance among {names}")


def fetch_instance(filing: Filing, client: _Client | None = None) -> Path:
    folder = RAW_DIR / filing.acc_nodash
    meta = folder / "filing.json"
    if meta.exists():
        inst = folder / json.loads(meta.read_text())["instance"]
        if inst.exists():
            return inst
    client = client or _Client()
    idx = _cached_json(client, ARCHIVE_URL.format(cik=CIK, acc_nodash=filing.acc_nodash, name="index.json"),
                       folder / "index.json")
    names = [item["name"] for item in idx["directory"]["item"]]
    inst_name = _pick_instance(names)
    inst = folder / inst_name
    if not inst.exists():
        inst.write_bytes(client.get(ARCHIVE_URL.format(cik=CIK, acc_nodash=filing.acc_nodash, name=inst_name)).content)
    meta.write_text(json.dumps({**filing.__dict__, "instance": inst_name,
                                "url": ARCHIVE_URL.format(cik=CIK, acc_nodash=filing.acc_nodash, name=inst_name)}))
    return inst


def fetch_all(filed_from: str = "2017-01-01") -> list[tuple[Filing, Path]]:
    client = _Client()
    filings = list_filings(client, filed_from=filed_from)
    return [(f, fetch_instance(f, client)) for f in filings]


def filing_url(filing: Filing) -> str:
    return (f"https://www.sec.gov/Archives/edgar/data/{CIK}/{filing.acc_nodash}/"
            f"{filing.accession}-index.htm")
