"""Cincinnati / Hamilton County, OH code enforcement lead scraper - configuration.

Cases:  City of Cincinnati Open Data "Code Enforcement" (Socrata, refreshed daily)
        https://data.cincinnati-oh.gov/d/cncm-znd6  (Cincinnati plus Norwood, Forest Park,
        Sycamore Twp, Blue Ash and other CAGIS member communities)
Owners: CAGIS quarterly Hamilton County parcel CSV (owner, mailing address, parcel, value)
        https://cagis.org/Opendata/Quarterly_GIS_Data/
"""
from pathlib import Path

STATE = "OH"
COUNTY = "Hamilton"

SODA_URL = "https://data.cincinnati-oh.gov/resource/cncm-znd6.json"
PAGE_SIZE = 50000
# Closed cases still worth keeping for a year: the owner didn't fix or pay.
STRONG_CLOSED_STATUSES = [
    "Costs have been Assessed on Tax Bill", "Owner Billed", "Property Owner Billed for Cleaning",
    "Refer to Abandoned Property Program", "Closed - Already in Abandoned Property Program",
    "Costs Cannot be Collected",
]
STRONG_CLOSED_DAYS = 365

CAGIS_FOLDER = "https://cagis.org/Opendata/Quarterly_GIS_Data/"
CASE_URL = "https://cagismaps.hamilton-co.org/PropertyActivity/CagisReport?APD={case}"

# Case categories: (label, base score, match words in comp_type_desc / sub_type_desc). First match wins.
CATEGORIES = [
    ("Demolition order", 40, ["DEMOLITION", "DEMOLISH"]),
    ("Vacant / barricaded building", 35, ["BARRICAD", "VACANT", "ABANDONED PROPERTY"]),
    ("Lead paint order", 25, ["LEAD PAINT"]),
    ("Building / housing code", 20, ["BUILDINGS WITH RESIDENCES", "COMMERCIAL BUILDINGS", "PROPERTY MAINTENANCE",
                                     "PROPERTY CODE", "BUILDING VIOLATION", "BUILDING CODE", "CONCENTRATED",
                                     "NEIGHBORHOOD CODE", "LEGACY CODE", "CODE ENFORCEMENT (FOREST PARK)",
                                     "SYCAMORE CODE", "FP CODE", "BUILDING CONSTRUCTION", "RESPONSE TEAM"]),
    ("Zoning violation", 10, ["ZONING"]),
    ("Junk / abandoned vehicle", 8, ["VEHICLE", "JUNK VEH"]),
    ("Trash / weeds / dumping", 8, ["TALL GRASS", "LITTER", "WEED", "DUMPING", "LOT ABATEMENT", "GARBAGE"]),
]
# Case sub-types that say nothing about the property owner's situation.
SKIP_SUBTYPES = ["IMPROPER SET OUT", "EMPTY CANS", "RECYCLING", "TREE ON", "GRAFFITI", "FEMA", "WATER QUALITY",
                 "LITTER AMNESTY", "ANIMAL"]
STAGE_BONUSES = [  # (label, words in status, points) - highest first, only one applies
    ("costs assessed on tax bill", ["assessed on tax bill", "cannot be collected"], 15),
    ("abandoned property program", ["abandoned property"], 15),
    ("owner billed for city cleanup", ["owner billed", "billed for cleaning", "cleaned by dept"], 10),
    ("orders / final notice issued", ["orders issued", "final notice", "notice", "reissue"], 8),
]
CITY_NAMES = {"CINC": "CINCINNATI", "NORW": "NORWOOD", "FRST": "FOREST PARK", "FPRK": "FOREST PARK",
              "SYCA": "SYCAMORE TWP", "SYCT": "SYCAMORE TWP", "BLUA": "BLUE ASH", "BASH": "BLUE ASH"}
INSTITUTIONAL_WORDS = ["BANK", "MORTGAGE", "FEDERAL NATIONAL", "FANNIE", "FREDDIE", "HOUSING AUTHORITY",
                       "LAND REUTILIZATION", "LANDBANK", "LAND BANK", "PORT AUTHORITY", "CITY OF", "VILLAGE OF",
                       "BOARD OF", "HAMILTON COUNTY", "STATE OF OHIO", "SECRETARY OF HOUSING", "TOWNSHIP"]
FEED_MIN_SCORE = 40

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "raw"
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
HISTORY_JSON = DATA_DIR / "history.json"
STATE_JSON = DATA_DIR / "state.json"
GHL_CSV = DATA_DIR / "ghl_cincinnati_code_enforcement.csv"
DOCS_CSV = DOCS_DIR / "ghl_cincinnati_code_enforcement.csv"
DASHBOARD_JSON = DOCS_DIR / "cincinnati_code_enforcement.json"
FEED_JSON = DOCS_DIR / "cincinnati_feed.json"
