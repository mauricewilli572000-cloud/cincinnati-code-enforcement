#!/usr/bin/env python3
"""Cincinnati / Hamilton County code enforcement leads.

1. Pull open code enforcement cases (and recently closed ones where the owner didn't
   fix or pay) from Cincinnati Open Data.
2. Group by property, attach owner / mailing address / parcel from the CAGIS parcel file.
3. Score, keep the date each property was first seen, export dashboard JSON + GHL CSV.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import logging
import re
import shutil
import sys
from collections import Counter

import config
import leads as L
import sources

log = logging.getLogger("cincinnati_code_enforcement")
GHL_COLUMNS = [
    "First Name", "Last Name", "Company Name", "Phone", "Email",
    "Mailing Address", "Property Address", "City", "State", "Postal Code",
    "Parcel", "Lead Source", "Lead Type", "Score", "Open Records", "Delinquent Taxes",
    "Oldest Open Days", "In Foreclosure", "Out Of State Owner", "Case Numbers",
    "Violations", "Score Reasons", "Date Added", "Tags", "Owner Full Name",
]


def split_name(owner: str) -> tuple[str, str, str]:
    if not owner:
        return "", "", ""
    if L.owner_class(owner) in ("entity", "institutional"):
        return "", "", owner.title()
    o = re.split(r"\s+(?:&|AND)\s+", owner)[0].replace(",", " ")
    parts = o.split()
    return (" ".join(parts[1:]).title(), parts[0].title(), "") if len(parts) > 1 else ("", o.title(), "")


def tags(l: dict) -> str:
    t = ["cincinnati-code-enforcement"]
    if l["score"] >= 60:
        t.append("hot")
    if l["in_foreclosure"]:
        t.append("foreclosure-flag")
    if l["delinquent_taxes"]:
        t.append("tax-delinquent")
    if l["out_of_state_owner"]:
        t.append("out-of-state-owner")
    if any("Vacant" in x for x in l["lead_types"]):
        t.append("vacant")
    if any("Demolition" in x for x in l["lead_types"]):
        t.append("demolition")
    return ",".join(t)


def export(all_leads: list[dict], meta: dict) -> int:
    config.DOCS_DIR.mkdir(parents=True, exist_ok=True)
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.DASHBOARD_JSON.write_text(json.dumps({"meta": meta, "leads": all_leads}, separators=(",", ":")))
    feed = [l for l in all_leads if l["score"] >= config.FEED_MIN_SCORE]
    config.FEED_JSON.write_text(json.dumps({"meta": meta, "leads": feed}, separators=(",", ":")))
    n = 0
    with open(config.GHL_CSV, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(GHL_COLUMNS)
        for l in all_leads:
            if l["score"] < config.FEED_MIN_SCORE or not l["owner_name"]:
                continue
            first, last, company = split_name(l["owner_name"])
            w.writerow([first, last, company, "", "", l["mailing_address"], l["property_address"], l["city"].title(),
                        l["state"], l["zip"], l["parcel"], "Cincinnati Code Enforcement", "; ".join(l["lead_types"]),
                        l["score"], l["open_records"], l["delinquent_taxes"] or "", l["oldest_open_days"],
                        "Yes" if l["in_foreclosure"] else "", "Yes" if l["out_of_state_owner"] else "",
                        "; ".join(l["case_numbers"]), "; ".join(l["violation_types"]), "; ".join(l["score_reasons"]),
                        l["added_date"], tags(l), l["owner_name"]])
            n += 1
    shutil.copyfile(config.GHL_CSV, config.DOCS_CSV)
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force-cagis", action="store_true", help="re-download the parcel file even if unchanged")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    today = dt.date.today()
    state = json.loads(config.STATE_JSON.read_text()) if config.STATE_JSON.exists() else {}

    log.info("Fetching cases from %s", config.SODA_URL)
    cases = sources.fetch_cases(today)
    log.info("Cases: %d; jurisdictions %s", len(cases), Counter(c.get("city_id") for c in cases).most_common(12))
    signals = L.to_signals(cases)
    log.info("Signals kept: %d (%s)", len(signals), Counter(s["category"] for s in signals).most_common())
    wanted = {s["key"] for s in signals}

    url = sources.find_cagis_url(today)
    path = sources.download_cagis(config.RAW_DIR, url)
    parcels, _ = sources.read_cagis(path, wanted)
    log.info("CAGIS by address: owners found for %d of %d properties", len(parcels), len(wanted))

    # Truncated / unmatched case addresses: find the parcel at the case's map point instead.
    points = {}
    for s in signals:
        if s["key"] not in parcels and s["lat"] and s["lon"] and s["key"] not in points:
            points[s["key"]] = (s["lat"], s["lon"])
    cache = json.loads(config.POINT_CACHE_JSON.read_text()) if config.POINT_CACHE_JSON.exists() else {}
    located = sources.parcel_at_points(points, cache, config.PARCEL_MAP_MAX_PER_RUN)
    config.POINT_CACHE_JSON.parent.mkdir(parents=True, exist_ok=True)
    config.POINT_CACHE_JSON.write_text(json.dumps(cache, separators=(",", ":")), encoding="utf-8")
    if located:
        _, by_parcel = sources.read_cagis(path, set(), {sources.pid_key(v) for v in located.values()})
        for key, pid in located.items():
            info = by_parcel.get(sources.pid_key(pid))
            if info:
                parcels[key] = {**info, "matched_by": "map point"}
    log.info("CAGIS: owners found for %d of %d properties", len(parcels), len(wanted))

    leads = L.build_leads(signals, parcels, today)
    history = json.loads(config.HISTORY_JSON.read_text()) if config.HISTORY_JSON.exists() else {}
    for l in leads:
        h = history.setdefault(l["lead_id"], {"added_date": today.isoformat()})
        h["last_seen"] = today.isoformat()
        l["added_date"] = h["added_date"]
        l["last_seen"] = today.isoformat()
    meta = {
        "updated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "source": config.SODA_URL, "parcels": sources.unquote(url),
        "cases": len(cases), "leads": len(leads), "with_owner": sum(1 for l in leads if l["owner_name"]),
        "score_60_plus": sum(1 for l in leads if l["score"] >= 60),
    }
    n_csv = export(leads, meta)
    config.HISTORY_JSON.write_text(json.dumps(history, indent=0), encoding="utf-8")
    state.update({"last_run": today.isoformat(), "cagis_file": meta["parcels"]})
    config.STATE_JSON.write_text(json.dumps(state, indent=2), encoding="utf-8")
    log.info("Saved %d leads (%d with owner, %d scoring 60+), GHL rows %d", len(leads), meta["with_owner"],
             meta["score_60_plus"], n_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
