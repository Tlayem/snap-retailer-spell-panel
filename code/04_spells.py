#!/usr/bin/env python3
"""04_spells.py — authorization records -> store spells and location spells.

Definitions
  store spell     one Record ID's continuous SNAP authorization. Authorization
                  records of the same Record ID are merged when the next one starts
                  within GAP_DAYS of the running latest end date.
  location spell  one address (location_key) continuously hosting at least one
                  SNAP-authorized fixed-location retailer, any Record ID, merging gaps
                  of up to GAP_DAYS. Farmers' markets and delivery routes have no
                  location spells (their "address" is a market site or a route base).

Records with End Date before Authorization Date (45) are kept in the authorization
file but enter no spell.

GAP_DAYS defaults to 365 (author's ruling V1, the Retailer Churn and Food Access
convention). Pass another value to rebuild at a different window:
    python code/04_spells.py 0      # each authorization record is its own spell

Writes data/processed/authorizations_part1-3.csv.gz, store_spells.csv.gz,
location_spells.csv.gz and data/interim/spells_log.json.
"""
import json
import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
INT = ROOT / "data" / "interim"
OUT = ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)

GAP_DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 365
FILE_END = pd.Timestamp("2025-12-31")
FAR = pd.Timestamp("2099-12-31")


def merge_intervals(d, key, gap_days):
    """Assign a spell number to each row: rows of the same key whose start is within gap_days
    of the running max end (open = FAR) continue the current spell. Returns a Series aligned to d."""
    e = d["end_date"].fillna(FAR)
    order = np.lexsort((e.values, d["authorization_date"].values, d[key].values))
    s = d.iloc[order]
    ef = e.iloc[order]
    runmax = ef.groupby(s[key].values).cummax()
    prev = runmax.groupby(s[key].values).shift()
    new = prev.isna() | (s["authorization_date"] > prev + pd.Timedelta(days=gap_days))
    seq = new.astype(int).groupby(s[key].values).cumsum()
    return seq.reindex(d.index)


def main():
    log = {"GAP_DAYS": GAP_DAYS}
    r = pd.read_parquet(INT / "records_clean.parquet")
    geo = pd.read_parquet(INT / "records_geo.parquet")
    assert len(geo) == len(r)
    r = pd.concat([r, geo], axis=1)

    ok = ~r["end_before_auth"]
    r["in_spells"] = ok

    # ---------------- store spells
    seq = merge_intervals(r[ok], "record_id", GAP_DAYS)
    r["store_spell_id"] = pd.Series(pd.NA, index=r.index, dtype="string")
    r.loc[ok, "store_spell_id"] = r.loc[ok, "record_id"].astype(str) + "-" + seq.astype(str)

    s = r[ok].copy()
    s["end_f"] = s["end_date"].fillna(FAR)
    ss = s.groupby("store_spell_id").agg(
        record_id=("record_id", "first"),
        start_date=("authorization_date", "min"), end_f=("end_f", "max"), n_records=("record_id", "size"),
        start_placeholder_1930=("auth_placeholder_1930", "max"))
    ss["spell_number"] = ss.index.str.split("-").str[1].astype(int)
    ss["end_date"] = ss["end_f"].where(ss["end_f"] < FAR)
    ss = ss.drop(columns="end_f").reset_index()
    attrs = ["store_name", "store_type", "store_group", "state", "zip5", "county_fips", "tract_geoid", "geo_method",
             "location_key", "in_50_states_dc", "fixed_location"]
    first = r[ok].drop_duplicates("record_id").set_index("record_id")[attrs]
    ss = ss.join(first, on="record_id")
    endflag = r.loc[ok, ["record_id", "end_date", "end_on_batch_date"]].dropna(subset=["end_date"]) \
        .drop_duplicates(["record_id", "end_date"])
    ss = ss.merge(endflag, on=["record_id", "end_date"], how="left")
    ss["end_on_batch_date"] = ss["end_on_batch_date"].fillna(False).astype(bool)
    ss["open_at_file_end"] = ss["end_date"].isna()
    ss["end_within_window_of_file_end"] = ss["end_date"] > FILE_END - pd.Timedelta(days=GAP_DAYS)
    ss = ss.sort_values(["record_id", "spell_number"]).reset_index(drop=True)
    log["store_spells"] = len(ss)
    log["record_ids_in_spells"] = int(ss["record_id"].nunique())

    # ---------------- location spells (fixed-location retailers only)
    lk = ok & r["fixed_location"]
    keys = np.sort(r.loc[lk, "location_key"].unique())
    loc_id = pd.Series(np.arange(1, len(keys) + 1), index=keys)
    r["location_id"] = r["location_key"].map(loc_id).where(lk).astype("Int64")
    seq = merge_intervals(r[lk], "location_id", GAP_DAYS)
    r["location_spell_id"] = pd.Series(pd.NA, index=r.index, dtype="string")
    r.loc[lk, "location_spell_id"] = r.loc[lk, "location_id"].astype(str) + "-" + seq.astype(str)

    s = r[lk].copy()
    s["end_f"] = s["end_date"].fillna(FAR)
    s["is_large"] = s["store_group"] == "Large store"
    ls = s.groupby("location_spell_id").agg(
        location_id=("location_id", "first"),
        start_date=("authorization_date", "min"), end_f=("end_f", "max"), n_records=("record_id", "size"),
        n_record_ids=("record_id", "nunique"), any_large_store=("is_large", "max"),
        start_placeholder_1930=("auth_placeholder_1930", "max"))
    ls["spell_number"] = ls.index.str.split("-").str[1].astype(int)
    ls["end_date"] = ls["end_f"].where(ls["end_f"] < FAR)
    ls = ls.drop(columns="end_f").reset_index()
    # geography and address of the address's most recent record
    last = s.sort_values(["authorization_date", "record_id"]).groupby("location_id").last()[
        ["location_key", "street_number", "street_name", "city", "state", "zip5", "county_fips", "tract_geoid",
         "geo_method", "in_50_states_dc"]]
    ls = ls.join(last, on="location_id")
    ls["ever_large_store"] = ls["location_id"].isin(set(s.loc[s["is_large"], "location_id"]))
    ls["open_at_file_end"] = ls["end_date"].isna()
    ls["end_within_window_of_file_end"] = ls["end_date"] > FILE_END - pd.Timedelta(days=GAP_DAYS)
    ls = ls.sort_values(["location_id", "spell_number"]).reset_index(drop=True)
    log["location_spells"] = len(ls)
    log["locations"] = int(ls["location_id"].nunique())

    # ---------------- reproduction of the Retailer Churn and Food Access sample
    paper = ok & r["fixed_location"] & r["in_50_states_dc"]
    log["paper_sample_records"] = int(paper.sum())
    log["paper_sample_store_spells"] = int(r.loc[paper, "store_spell_id"].nunique())
    log["paper_sample_location_spells"] = int(r.loc[paper, "location_spell_id"].nunique())
    log["paper_sample_locations"] = int(r.loc[paper, "location_id"].nunique())

    # ---------------- write
    ss["location_id"] = ss["record_id"].map(r.drop_duplicates("record_id").set_index("record_id")["location_id"])
    cols = ["record_id", "store_spell_id", "location_id", "location_spell_id", "store_name", "store_type",
            "store_group", "street_number", "street_name", "additional_address", "city", "state", "zip5", "zip4",
            "county_fns", "county_fips", "tract_geoid", "geo_method", "county_agrees_fns", "latitude", "longitude",
            "coord_check", "coord_shared_locations", "authorization_date", "end_date", "auth_placeholder_1930",
            "end_before_auth", "end_on_batch_date", "in_50_states_dc", "fixed_location", "has_street_address"]
    a = r[cols].sort_values(["record_id", "authorization_date"])
    # three parts, split by Record ID, so each file stays well under GitHub's 25 MB browser-upload limit
    for old in OUT.glob("authorizations*.csv.gz"):
        old.unlink()
    cuts = [int(a["record_id"].iloc[len(a) * k // 3]) for k in (1, 2)]
    bounds = [None] + cuts + [None]
    for k in range(3):
        lo, hi = bounds[k], bounds[k + 1]
        m = pd.Series(True, index=a.index)
        if lo is not None:
            m &= a["record_id"] >= lo
        if hi is not None:
            m &= a["record_id"] < hi
        a[m].to_csv(OUT / f"authorizations_part{k + 1}.csv.gz", index=False, date_format="%Y-%m-%d")
    log["authorizations_split_record_ids"] = cuts
    sc = ["store_spell_id", "record_id", "spell_number", "start_date", "end_date", "n_records", "store_name",
          "store_type", "store_group", "state", "zip5", "county_fips", "tract_geoid", "geo_method", "location_id",
          "start_placeholder_1930", "end_on_batch_date", "open_at_file_end", "end_within_window_of_file_end",
          "in_50_states_dc", "fixed_location"]
    ss[sc].to_csv(OUT / "store_spells.csv.gz", index=False, date_format="%Y-%m-%d")
    lc = ["location_spell_id", "location_id", "spell_number", "start_date", "end_date", "n_records", "n_record_ids",
          "any_large_store", "ever_large_store", "location_key", "street_number", "street_name", "city", "state",
          "zip5", "county_fips", "tract_geoid", "geo_method", "start_placeholder_1930", "open_at_file_end",
          "end_within_window_of_file_end", "in_50_states_dc"]
    ls[lc].to_csv(OUT / "location_spells.csv.gz", index=False, date_format="%Y-%m-%d")
    ss[sc].to_parquet(INT / "store_spells.parquet", index=False)
    ls[lc].to_parquet(INT / "location_spells.parquet", index=False)
    a.to_parquet(INT / "authorizations.parquet", index=False)
    (INT / "spells_log.json").write_text(json.dumps(log, indent=2))
    print(json.dumps(log, indent=2))


if __name__ == "__main__":
    main()
