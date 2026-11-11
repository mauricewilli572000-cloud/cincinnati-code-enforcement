"""Group cases by property, attach owners, score (0-100). Same lead layout as cleveland-code-enforcement."""
from __future__ import annotations

import datetime as dt
import hashlib
import re

import config
from addr import normalize_address
from sources import categorize

ENTITY_RE = re.compile(r"\b(LLC|L L C|INC|CORP|CORPORATION|COMPANY|CO|LTD|LP|LLP|TRUST|TRUSTEE|BANK|ASSOCIATION|"
                       r"ASSN|CHURCH|PROPERTIES|HOLDINGS|INVESTMENTS|GROUP|PARTNERS|ESTATE|AUTHORITY)\b")


def owner_class(name: str) -> str:
    n = (name or "").upper()
    if not n:
        return ""
    if any(w in n for w in config.INSTITUTIONAL_WORDS):
        return "institutional"
    return "entity" if ENTITY_RE.search(n) else "individual"


def _days(iso: str, today: dt.date) -> int:
    try:
        return max(0, (today - dt.date.fromisoformat(iso[:10])).days)
    except (TypeError, ValueError):
        return 0


def to_signals(cases: list[dict]) -> list[dict]:
    out = []
    for c in cases:
        cat = categorize(c)
        key = normalize_address(c.get("full_address"))
        if not cat or not key:
            continue
        out.append({
            "key": key, "address": (c.get("full_address") or "").strip(), "category": cat[0], "base": cat[1],
            "case_number": c.get("number_key", ""), "type": (c.get("sub_type_desc") or c.get("comp_type_desc") or "").strip(),
            "status": c.get("data_status_display") or "", "open": c.get("status_class") == "OPEN",
            "date": (c.get("entered_date") or "")[:10], "updated": (c.get("last_updated") or "")[:10],
            "city": config.CITY_NAMES.get(c.get("city_id", ""), c.get("city_id", "")),
            "neighborhood": (c.get("neighborhood") or "").title(),
        })
    return out


def build_leads(signals: list[dict], parcels: dict[str, dict], today: dt.date) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for s in signals:
        groups.setdefault(s["key"], []).append(s)
    leads = []
    for key, sigs in groups.items():
        sigs.sort(key=lambda s: s["date"], reverse=True)
        cats = sorted({s["category"] for s in sigs}, key=lambda c: -max(x["base"] for x in sigs if x["category"] == c))
        score = max(s["base"] for s in sigs)
        reasons = [cats[0] + f" ({score})"]
        if len(sigs) > 1:
            b = min(20, 5 * (len(sigs) - 1)); score += b; reasons.append(f"{len(sigs)} records (+{b})")
        if len(cats) > 1:
            score += 10; reasons.append("multiple enforcement types (+10)")
        oldest = max(_days(s["date"], today) for s in sigs if s["open"]) if any(s["open"] for s in sigs) else 0
        if oldest > 180:
            score += 15; reasons.append("open > 180 days (+15)")
        elif oldest > 90:
            score += 10; reasons.append("open > 90 days (+10)")
        stage = " ".join(s["status"].lower() for s in sigs)
        for label, words, pts in config.STAGE_BONUSES:
            if any(w in stage for w in words):
                score += pts; reasons.append(f"{label} (+{pts})")
                break

        p = parcels.get(key)
        mailing = p["mailing_address"] if p else ""
        csz = (p["mailing_csz"] if p else "").upper()
        out_state = bool(csz) and not re.search(r"\bOH\b", csz)
        if p:
            if out_state:
                score += 15; reasons.append("owner mails out of state (+15)")
            elif mailing and normalize_address(mailing) != key:
                score += 8; reasons.append("absentee owner (+8)")
            cls = owner_class(p["owner_name"])
            if cls == "individual":
                score += 10; reasons.append("individual owner (+10)")
            elif cls == "institutional":
                score -= 15; reasons.append("institutional/government owner (-15)")
            if p["in_foreclosure"]:
                score += 25; reasons.append("county foreclosure flag (+25)")
            if p["delinquent_taxes"] > 0:
                score += 10; reasons.append(f"delinquent taxes ${p['delinquent_taxes']:,.0f} (+10)")
        else:
            reasons.append("owner not found")

        head = sigs[0]
        leads.append({
            "lead_id": hashlib.sha1(key.encode()).hexdigest()[:12],
            "property_address": head["address"],
            "city": next((s["city"] for s in sigs if s["city"]), "CINCINNATI"),
            "state": config.STATE,
            "zip": "",
            "parcel": p["parcel"] if p else "",
            "owner_name": p["owner_name"] if p else "",
            "owner_is_entity": bool(p and owner_class(p["owner_name"]) in ("entity", "institutional")),
            "owner_class": owner_class(p["owner_name"]) if p else "",
            "mailing_address": mailing,
            "out_of_state_owner": bool(p and out_state),
            "lead_types": cats,
            "open_records": len(sigs),
            "case_numbers": sorted({s["case_number"] for s in sigs if s["case_number"]}),
            "violation_types": sorted({s["type"] for s in sigs if s["type"]})[:6],
            "statuses": sorted({s["status"] for s in sigs if s["status"]})[:6],
            "description": head["type"],
            "oldest_open_days": oldest,
            "latest_date": head["date"],
            "total_fines": 0,
            "neighborhood": next((s["neighborhood"] for s in sigs if s["neighborhood"]), ""),
            "market_value": p["market_value"] if p else None,
            "delinquent_taxes": p["delinquent_taxes"] if p else 0,
            "in_foreclosure": bool(p and p["in_foreclosure"]),
            "case_url": config.CASE_URL.format(case=head["case_number"]),
            "score": max(0, min(100, score)),
            "score_reasons": reasons,
        })
    leads.sort(key=lambda l: (-l["score"], l["property_address"]))
    return leads
