import datetime as dt

import leads as L
from sources import categorize


def case(**kw):
    base = {"number_key": "B1", "comp_type_desc": "Code Enforcement - Buildings with Residences",
            "sub_type_desc": "RES CODE STANDARD", "entered_date": "2026-01-02T00:00:00.000",
            "data_status_display": "Orders Issued", "status_class": "OPEN", "city_id": "CINC",
            "full_address": "2614 MONTANA AV", "neighborhood": "WESTWOOD"}
    base.update(kw)
    return base


def test_categories():
    assert categorize(case())[0] == "Building / housing code"
    assert categorize(case(sub_type_desc="VACANT RES BLDG-BARRC PRIORITY"))[0] == "Vacant / barricaded building"
    assert categorize(case(comp_type_desc="Trash/Litter/Tall Grass Complaint", sub_type_desc="Trash, improper set out")) is None


def test_grouping_and_owner():
    sigs = L.to_signals([case(), case(number_key="B2", sub_type_desc="VACANT RES BLDG-BARRC PRIORITY",
                                      full_address="2614 Montana Ave")])
    parcels = {"2614 MONTANA AVE": {"parcel": "2090003024300", "owner_name": "SMITH JOHN", "mailing_name": "",
                                    "mailing_address": "9 ELM ST, DALLAS TX 75201", "mailing_csz": "DALLAS TX 75201",
                                    "market_value": 60000, "land_use": "510", "exlucode": "SF",
                                    "in_foreclosure": False, "delinquent_taxes": 1200.0, "has_mortgage_bank": False, "homestead": False, "rental_registered": False}}
    leads = L.build_leads(sigs, parcels, dt.date(2026, 11, 10))
    assert len(leads) == 1
    l = leads[0]
    assert l["open_records"] == 2 and l["lead_types"][0] == "Vacant / barricaded building"
    assert l["out_of_state_owner"] and l["parcel"] == "2090003024300" and l["score"] >= 80


def test_cagis_suffix_codes():
    from addr import normalize_address
    assert normalize_address("1250 OBERLIN BV") == normalize_address("1250 OBERLIN BLVD")
