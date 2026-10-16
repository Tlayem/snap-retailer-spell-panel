#!/usr/bin/env python3
"""02_clean.py — FNS historical file -> cleaned authorization records (interim).

One row per FNS authorization record. Every record is kept; problems are flagged,
never silently dropped. Writes data/interim/records_clean.parquet and
data/interim/clean_log.json.

Cleaning steps
  - trim whitespace; FNS text fields are otherwise left as published
  - ZIP Code restored to 5 digits (the file drops leading zeros: "2134" -> "02134");
    Zip4 restored to 4 digits
  - dates parsed (MM/DD/YYYY); empty End Date = authorization open on 31 Dec 2025
  - coordinates: (0, 0) and out-of-range values set to missing and flagged
  - flags: 1 Jan 1930 placeholder authorization date; End Date before
    Authorization Date; End Date shared by >= BATCH_MIN records nationally
    (administrative batch action); 50 states + DC; fixed-location retailer
    (not a farmers' market or delivery route)
  - address key `location_key` = street number | standardized street name | ZIP5,
    identical in construction to Retailer Churn and Food Access (v0.1.0) so the two
    releases agree; records without a street address are keyed by Record ID

Usage:  python code/02_clean.py
"""
import json
import pathlib

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "raw" / "extracted" / "Historical SNAP Retailer Locator Data 2005-2025.csv"
INT = ROOT / "data" / "interim"
INT.mkdir(parents=True, exist_ok=True)

BATCH_MIN = 1000
FILE_END = pd.Timestamp("2025-12-31")
STATES_50_DC = set("""AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV
NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY""".split())
NON_FIXED = {"Farmers' Market", "Delivery Route"}
GROUP = {
    "Supermarket": "Large store", "Super Store": "Large store", "Large Grocery Store": "Large store",
    "Medium Grocery Store": "Grocery", "Small Grocery Store": "Grocery",
    "Combination Grocery/Other": "Grocery", "Food Buying Co-op": "Grocery",
    "Convenience Store": "Convenience",
    "Meat/Poultry Specialty": "Specialty", "Bakery Specialty": "Specialty",
    "Seafood Specialty": "Specialty", "Fruits/Veg Specialty": "Specialty",
    "Military Commissary": "Other", "Wholesaler": "Other", "Unknown": "Other",
    "Farmers' Market": "Farmers' market", "Delivery Route": "Delivery route",
}


def street_std(s):
    """Light street-name standardization, exactly as in Retailer Churn and Food Access v0.1.0."""
    s = s.fillna("").str.upper().str.replace(r"[^A-Z0-9 ]", " ", regex=True)
    for full, abbr in [("STREET", "ST"), ("AVENUE", "AVE"), ("ROAD", "RD"), ("HIGHWAY", "HWY"),
                       ("DRIVE", "DR"), ("BOULEVARD", "BLVD")]:
        s = s.str.replace(rf"\b({full})\b", abbr, regex=True)
    return s.str.replace(r"\s+", " ", regex=True).str.strip()


def main():
    log = {}
    raw = pd.read_csv(SRC, dtype=str, encoding="utf-8-sig", keep_default_na=False)
    raw = raw.apply(lambda s: s.str.strip())
    log["records_raw"] = len(raw)
    log["record_ids_raw"] = int(raw["Record ID"].nunique())

    r = pd.DataFrame({
        "record_id": raw["Record ID"].astype("int64"),
        "store_name": raw["Store Name"],
        "store_type": raw["Store Type"],
        "street_number": raw["Street Number"],
        "street_name": raw["Street Name"],
        "additional_address": raw["Additional Address"],
        "city": raw["City"],
        "state": raw["State"],
        "zip5": raw["Zip Code"].str.zfill(5),
        "zip4": raw["Zip4"].where(raw["Zip4"] == "", raw["Zip4"].str.zfill(4)),
        "county_fns": raw["County"],
    })
    log["zip_codes_restored_leading_zero"] = int((raw["Zip Code"].str.len() < 5).sum())
    r["store_group"] = r["store_type"].map(GROUP)
    assert r["store_group"].notna().all(), set(r.loc[r["store_group"].isna(), "store_type"])

    # coordinates
    lat = pd.to_numeric(raw["Latitude"], errors="coerce")
    lon = pd.to_numeric(raw["Longitude"], errors="coerce")
    zero = (lat == 0) & (lon == 0)
    bad_range = ~zero & (lat.isna() | lon.isna() | ~lat.between(-15, 72) | ~lon.between(-180, 180))
    r["latitude_fns"] = lat.where(~zero & ~bad_range)
    r["longitude_fns"] = lon.where(~zero & ~bad_range)
    r["coord_status"] = np.select([zero, bad_range], ["zero", "out_of_range"], "present")
    log["coords_zero"] = int(zero.sum())
    log["coords_out_of_range"] = int(bad_range.sum())

    # dates
    r["authorization_date"] = pd.to_datetime(raw["Authorization Date"], format="%m/%d/%Y")
    r["end_date"] = pd.to_datetime(raw["End Date"].replace("", None), format="%m/%d/%Y")
    r["auth_placeholder_1930"] = r["authorization_date"] == pd.Timestamp("1930-01-01")
    r["end_before_auth"] = r["end_date"].notna() & (r["end_date"] < r["authorization_date"])
    assert (r["end_date"].dropna() <= FILE_END).all()
    end_counts = r["end_date"].value_counts()
    batch = set(end_counts[end_counts >= BATCH_MIN].index)
    r["end_on_batch_date"] = r["end_date"].isin(batch)
    log["batch_end_dates"] = sorted(d.strftime("%Y-%m-%d") for d in batch)
    log["records_auth_placeholder_1930"] = int(r["auth_placeholder_1930"].sum())
    log["records_end_before_auth"] = int(r["end_before_auth"].sum())
    log["records_open"] = int(r["end_date"].isna().sum())
    log["records_end_on_batch_date"] = int(r["end_on_batch_date"].sum())

    # coverage flags
    r["in_50_states_dc"] = r["state"].isin(STATES_50_DC)
    r["fixed_location"] = ~r["store_type"].isin(NON_FIXED)
    log["records_outside_50_states_dc"] = int((~r["in_50_states_dc"]).sum())
    log["records_not_fixed_location"] = int((~r["fixed_location"]).sum())
    log["states_in_file"] = sorted(r["state"].unique())

    # address key
    no = r["street_number"].str.upper()
    st = street_std(r["street_name"])
    has = (no != "") & (st != "")
    r["has_street_address"] = has
    r["location_key"] = np.where(has, no + "|" + st + "|" + r["zip5"], "RID|" + r["record_id"].astype(str))
    log["records_without_street_address"] = int((~has).sum())

    # shared coordinates: how many distinct addresses carry exactly this coordinate pair
    cp = r.loc[r["coord_status"] == "present", ["latitude_fns", "longitude_fns", "location_key"]]
    n = cp.drop_duplicates().groupby(["latitude_fns", "longitude_fns"]).size().rename("coord_shared_locations")
    r = r.join(n, on=["latitude_fns", "longitude_fns"])
    r["coord_shared_locations"] = r["coord_shared_locations"].fillna(0).astype(int)

    r.to_parquet(INT / "records_clean.parquet", index=False)
    (INT / "clean_log.json").write_text(json.dumps(log, indent=2))
    print(json.dumps({k: v for k, v in log.items() if k != "batch_end_dates"}, indent=2))


if __name__ == "__main__":
    main()
