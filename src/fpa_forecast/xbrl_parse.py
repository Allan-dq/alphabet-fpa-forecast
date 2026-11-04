"""Parse an XBRL instance document into a long table of numeric facts.

Each fact keeps its period (start/end or instant) and its explicit dimension
members, which is where Alphabet tags revenue by type
(srt:ProductOrServiceAxis) and operating income by segment
(us-gaap:StatementBusinessSegmentsAxis). The SEC companyfacts API drops these
dimensions, so we read the instance documents directly.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from lxml import etree

XBRLI = "http://www.xbrl.org/2003/instance"
XBRLDI = "http://xbrl.org/2006/xbrldi"


def _short_prefix(ns: str | None, nsmap: dict[str, str]) -> str:
    if ns is None:
        return ""
    if "fasb.org/us-gaap" in ns:
        return "us-gaap"
    if "fasb.org/srt" in ns:
        return "srt"
    if "xbrl.sec.gov/dei" in ns:
        return "dei"
    if "abc.xyz" in ns or "google.com" in ns or "/goog/" in ns:
        return "goog"
    for p, uri in nsmap.items():
        if uri == ns and p:
            return p
    return ns


def _qname_to_short(qname: str, nsmap: dict[str, str]) -> str:
    """Normalise 'prefix:Local' (prefix as declared in this file) to a stable prefix."""
    if ":" not in qname:
        return qname
    p, local = qname.split(":", 1)
    return f"{_short_prefix(nsmap.get(p), nsmap)}:{local}"


def parse_instance(path: Path) -> pd.DataFrame:
    tree = etree.parse(str(path))
    root = tree.getroot()
    nsmap = {k or "": v for k, v in root.nsmap.items()}

    contexts: dict[str, dict] = {}
    for ctx in root.iter(f"{{{XBRLI}}}context"):
        cid = ctx.get("id")
        period = ctx.find(f"{{{XBRLI}}}period")
        start = period.findtext(f"{{{XBRLI}}}startDate")
        end = period.findtext(f"{{{XBRLI}}}endDate")
        instant = period.findtext(f"{{{XBRLI}}}instant")
        dims = []
        for mem in ctx.iter(f"{{{XBRLDI}}}explicitMember"):
            axis = _qname_to_short(mem.get("dimension"), nsmap)
            member = _qname_to_short(mem.text.strip(), nsmap)
            dims.append(f"{axis}={member}")
        typed = list(ctx.iter(f"{{{XBRLDI}}}typedMember"))
        contexts[cid] = {
            "start": start, "end": end or instant, "instant": instant is not None,
            "dims": "|".join(sorted(dims)), "typed_dims": len(typed) > 0,
        }

    rows = []
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        cref = el.get("contextRef")
        if cref is None or el.get("unitRef") is None:
            continue
        text = (el.text or "").strip()
        if not text:
            continue
        try:
            value = float(text)
        except ValueError:
            continue
        qn = etree.QName(el)
        ctx = contexts[cref]
        rows.append({
            "concept": f"{_short_prefix(qn.namespace, nsmap)}:{qn.localname}",
            "value": value,
            "unit": el.get("unitRef"),
            "decimals": el.get("decimals"),
            "start": ctx["start"],
            "end": ctx["end"],
            "instant": ctx["instant"],
            "dims": ctx["dims"],
            "typed_dims": ctx["typed_dims"],
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # The same fact can appear more than once (e.g. tagged in two tables).
    return df.drop_duplicates(subset=["concept", "start", "end", "dims", "value", "unit"]).reset_index(drop=True)
