"""Fetch code enforcement cases (Socrata) and the CAGIS parcel file."""
from __future__ import annotations

import csv
import datetime as dt
import logging
import re
import time
from pathlib import Path
from urllib.parse import quote, unquote, urljoin

import config
from addr import normalize_address

log = logging.getLogger(__name__)
csv.field_size_limit(10_000_000)

try:
    from curl_cffi import requests as _http
    S = _http.Session(impersonate="chrome")
except Exception:  # pragma: no cover
    import requests as _http
    S = _http.Session()


def get(url, **kw):
    last = None
    for attempt in range(4):
        try:
            r = S.get(url, timeout=kw.pop("timeout", 300), **kw)
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}"
        except Exception as e:  # noqa: BLE001
            last = str(e)
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"GET {url} failed: {last}")


# ----------------------------------------------------------------- cases
FIELDS = ["number_key", "comp_type_desc", "sub_type_desc", "entered_date", "last_updated", "data_status_display",
          "status_class", "city_id", "neighborhood", "full_address", "latitude", "longitude", "url"]


def fetch_cases(today: dt.date) -> list[dict]:
    """Open cases + recently closed cases where the owner didn't fix or pay."""
    since = (today - dt.timedelta(days=config.STRONG_CLOSED_DAYS)).isoformat()
    strong = ",".join("'" + s.replace("'", "''") + "'" for s in config.STRONG_CLOSED_STATUSES)
    where = f"status_class='OPEN' OR (data_status_display in ({strong}) AND last_updated >= '{since}')"
    out, offset = [], 0
    while True:
        params = {"$select": ",".join(FIELDS), "$where": where, "$order": "number_key",
                  "$limit": config.PAGE_SIZE, "$offset": offset}
        batch = get(config.SODA_URL, params=params).json()
        out.extend(batch)
        log.info("  cases %d-%d", offset, offset + len(batch))
        if len(batch) < config.PAGE_SIZE:
            break
        offset += config.PAGE_SIZE
    return out


def categorize(case: dict) -> tuple[str, int] | None:
    text = f"{case.get('comp_type_desc', '')} {case.get('sub_type_desc', '')}".upper()
    if any(w in text for w in config.SKIP_SUBTYPES):
        return None
    for label, base, words in config.CATEGORIES:
        if any(w in text for w in words):
            return label, base
    return None


# ----------------------------------------------------------------- CAGIS parcels
NAME_RE = re.compile(r"Hamilton[ _%20]*County[ _%20]*Parcels[ _%20]*([A-Za-z]+)[ _%20]*(\d{4})\.csv", re.I)
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]


def _file_date(name: str) -> tuple[int, int]:
    m = NAME_RE.search(unquote(name))
    if not m or m.group(1).lower() not in MONTHS:
        return (0, 0)
    return (int(m.group(2)), MONTHS.index(m.group(1).lower()) + 1)


def find_cagis_url(today: dt.date) -> str:
    try:
        html = get(config.CAGIS_FOLDER, timeout=60).text
        names = [h for h in re.findall(r'href=["\']([^"\']+\.csv)["\']', html, re.I) if NAME_RE.search(unquote(h))]
        if names:
            return urljoin(config.CAGIS_FOLDER, max(names, key=_file_date))
    except Exception as e:  # noqa: BLE001
        log.info("CAGIS folder listing not readable (%s) - trying recent month names", e)
    for back in range(15):
        y, m = today.year, today.month - back
        while m <= 0:
            y, m = y - 1, m + 12
        url = config.CAGIS_FOLDER + quote(f"Hamilton County Parcels {MONTHS[m - 1].title()} {y}.csv")
        try:
            if S.head(url, timeout=60).status_code == 200:
                return url
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError("No 'Hamilton County Parcels <Month> <Year>.csv' found at CAGIS")


def download_cagis(dest_dir: Path, url: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "cagis_parcels.csv"
    log.info("Downloading CAGIS parcels: %s", unquote(url))
    r = get(url, timeout=900)
    dest.write_bytes(r.content)
    log.info("  %.0f MB", dest.stat().st_size / 1e6)
    return dest


def _num(v) -> float:
    try:
        return float(re.sub(r"[^0-9.\-]", "", str(v or "")) or 0)
    except ValueError:
        return 0.0


def _g(row, k) -> str:
    return re.sub(r"\s+", " ", str(row.get(k) or "")).strip()


def pid_key(v) -> str:
    return re.sub(r"\D", "", str(v or "")).lstrip("0")


def read_cagis(path: Path, wanted_keys: set[str], wanted_parcels: set[str] | None = None
               ) -> tuple[dict[str, dict], dict[str, dict]]:
    """({normalized address: best parcel info}, {parcel id: info}) for the addresses / parcels we want."""
    wanted_parcels = wanted_parcels or set()
    best: dict[str, tuple[float, dict]] = {}
    by_parcel: dict[str, dict] = {}
    with path.open(encoding="latin-1", newline="") as f:
        for row in csv.DictReader(f):
            no, st, sf, dr = _g(row, "ADDRNO"), _g(row, "ADDRST"), _g(row, "ADDRSF"), _g(row, "LOC_ST_DIR")
            # index with and without the street direction - case addresses don't always carry it
            keys = {normalize_address(" ".join(p for p in (no, st, sf) if p)),
                    normalize_address(" ".join(p for p in (no, dr, st, sf) if p))}
            keys = {k for k in keys if k and k in wanted_keys}
            pk = pid_key(_g(row, "PARCELID"))
            if not keys and pk not in wanted_parcels:
                continue
            impr = _num(row.get("MKTIMP"))
            rank = (1 if _g(row, "MLTOWN") in ("0", "00", "") else 0) * 1e12 + impr
            book, page, parcel = _g(row, "BOOK"), _g(row, "PAGE"), _g(row, "PARCEL")
            parcel_id = _g(row, "PROPTYID") or (f"{book.zfill(3)}{page.zfill(4)}{parcel.zfill(4)}00"
                                                if book and page and parcel else "")
            # The tax-bill (MLADR) address is often the mortgage servicer, so prefer the owner's own address.
            own1 = " ".join(p for p in (_g(row, "OWNAD1"), _g(row, "OWNAD1A")) if p)
            own_csz = " ".join(p for p in (_g(row, "OWNADCITY"), _g(row, "OWNADSTATE"), _g(row, "OWNADZIP")[:5]) if p)
            if own1 and own_csz:
                mail1, mail2 = own1, own_csz
            else:
                mail1, mail2 = _g(row, "MLADR1"), _g(row, "MLADR2")
            info = {
                "parcel": re.sub(r"\D", "", parcel_id),
                "owner_name": " ".join(p for p in (_g(row, "OWNNM1"), _g(row, "OWNNM2")) if p),
                "mailing_name": _g(row, "MLNM1"),
                "mailing_address": ", ".join(p for p in (mail1, mail2) if p),
                "mailing_csz": mail2,
                "market_value": _num(row.get("MKTLND")) + impr,
                "land_use": _g(row, "CLASS"),
                "exlucode": _g(row, "EXLUCODE"),
                "in_foreclosure": _g(row, "FORECL_FLAG").upper() in ("Y", "YES", "1", "T"),
                "delinquent_taxes": _num(row.get("DELQ_TAXES") or row.get("DELIQ_TAXES")),
                "homestead": _g(row, "HMSD_FLAG").upper() in ("Y", "YES", "1", "T"),
                "rental_registered": _g(row, "RENT_REG_FLAG").upper() in ("Y", "YES", "1", "T"),
                "has_mortgage_bank": bool(_g(row, "BANKCD").strip("0")),
            }
            info["address"] = " ".join(p for p in (no, dr, st, sf) if p)
            if pk in wanted_parcels and (pk not in by_parcel or rank > by_parcel[pk]["_rank"]):
                by_parcel[pk] = {**info, "_rank": rank}
            for key in keys:
                if key not in best or rank > best[key][0]:
                    best[key] = (rank, info)
    return {k: v for k, (_, v) in best.items()}, by_parcel


def parcel_at_points(points: dict[str, tuple[float, float]], cache: dict, max_queries: int) -> dict[str, str]:
    """{key: parcel id} by asking the county parcel map which parcel each case point falls in.

    Used for case addresses the city truncated ('43 OBERLIN BLVD'). Cached by point, forever.
    """
    out, done = {}, 0
    for key, (lat, lon) in points.items():
        pt = f"{lat:.6f},{lon:.6f}"
        if pt not in cache:
            if done >= max_queries:
                continue
            done += 1
            try:
                r = S.get(config.PARCEL_MAP_QUERY, timeout=60, params={
                    "geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint", "inSR": 4326,
                    "spatialRel": "esriSpatialRelIntersects", "outFields": "PARCELID",
                    "returnGeometry": "false", "f": "json"})
                feats = r.json().get("features", [])
                cache[pt] = feats[0]["attributes"]["PARCELID"] if feats else ""
            except Exception as e:  # noqa: BLE001 - try again next run
                log.debug("point lookup failed %s: %s", pt, e)
                continue
            time.sleep(config.PARCEL_MAP_DELAY)
        if cache.get(pt):
            out[key] = cache[pt]
    log.info("Parcel map: %d new lookups, %d properties located by point", done, len(out))
    return out
