#!/usr/bin/env python3
"""05_panels.py — spells -> annual stock and flows (national, county, tract).

For each calendar year Y in 2006-2025:
  stock_jan1  spells active on 1 January Y (start < 1 Jan Y <= end, open = active)
  entries     spells starting during Y
  exits       spells ending during Y; left empty for 2025, because a 2025 exit cannot
              yet be told apart from a gap that a 2026 re-authorization would close

Stores: all store spells, by store_group (fixed-location groups, farmers' markets,
delivery routes); "All fixed-location" sums the five fixed-location groups.
Locations: location spells (fixed-location retailers only).

Writes data/processed/national_year.csv, county_year.csv.gz, tract_year.csv.gz.
"""
import json
import pathlib

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
INT = ROOT / "data" / "interim"
OUT = ROOT / "data" / "processed"
YEARS = range(2006, 2026)
LAST_EXIT_YEAR = 2024
FAR = pd.Timestamp("2099-12-31")
FIXED = ["Large store", "Grocery", "Convenience", "Specialty", "Other"]


def flows(sp, keys):
    start = sp["start_date"].values
    end = sp["end_date"].fillna(FAR).values
    endna = sp["end_date"].values
    rows = []
    for y in YEARS:
        j1, d31 = np.datetime64(f"{y}-01-01"), np.datetime64(f"{y}-12-31")
        t = sp[keys].copy()
        t["stock_jan1"] = (start < j1) & (end >= j1)
        t["entries"] = (start >= j1) & (start <= d31)
        t["exits"] = (endna >= j1) & (endna <= d31)
        a = t.groupby(keys, dropna=False)[["stock_jan1", "entries", "exits"]].sum().reset_index() if keys else \
            t[["stock_jan1", "entries", "exits"]].sum().to_frame().T
        a["year"] = y
        rows.append(a)
    f = pd.concat(rows, ignore_index=True)
    f[["stock_jan1", "entries", "exits"]] = f[["stock_jan1", "entries", "exits"]].astype("Int64")
    f.loc[f["year"] > LAST_EXIT_YEAR, "exits"] = pd.NA
    return f


def with_all_fixed(f, keys):
    fx = f[f["store_group"].isin(FIXED)].groupby(keys + ["year"])[["stock_jan1", "entries", "exits"]] \
        .sum(min_count=1).reset_index()
    fx["store_group"] = "All fixed-location"
    return pd.concat([fx, f], ignore_index=True)


def rates(f):
    f["entry_rate"] = (f["entries"] / f["stock_jan1"]).astype(float).round(5)
    f["exit_rate"] = (f["exits"] / f["stock_jan1"]).astype(float).round(5)
    return f


def main():
    ss = pd.read_parquet(INT / "store_spells.parquet")
    ls = pd.read_parquet(INT / "location_spells.parquet")
    log = {}

    # national
    n_s = with_all_fixed(flows(ss, ["store_group"]), [])
    n_s.insert(0, "unit", "store")
    n_l = flows(ls, [])
    n_l.insert(0, "unit", "location")
    n_l["store_group"] = "All fixed-location"
    n_s50 = with_all_fixed(flows(ss[ss["in_50_states_dc"]], ["store_group"]), [])
    n_s50.insert(0, "unit", "store")
    n_l50 = flows(ls[ls["in_50_states_dc"]], [])
    n_l50.insert(0, "unit", "location")
    n_l50["store_group"] = "All fixed-location"
    nat = pd.concat([n_s.assign(coverage="all"), n_l.assign(coverage="all"),
                     n_s50.assign(coverage="50 states + DC"), n_l50.assign(coverage="50 states + DC")])
    nat = rates(nat)[["coverage", "unit", "store_group", "year", "stock_jan1", "entries", "exits", "entry_rate",
                      "exit_rate"]].sort_values(["coverage", "unit", "store_group", "year"])
    nat.to_csv(OUT / "national_year.csv", index=False)

    # county
    c_s = with_all_fixed(flows(ss[ss["county_fips"].notna()], ["county_fips", "store_group"]), ["county_fips"])
    c_s.insert(0, "unit", "store")
    c_l = flows(ls[ls["county_fips"].notna()], ["county_fips"])
    c_l.insert(0, "unit", "location")
    c_l["store_group"] = "All fixed-location"
    cy = pd.concat([c_s, c_l], ignore_index=True)
    cy = cy[(cy["stock_jan1"] > 0) | (cy["entries"] > 0) | (cy["exits"].fillna(0) > 0)]
    cy = rates(cy)[["county_fips", "year", "unit", "store_group", "stock_jan1", "entries", "exits", "entry_rate",
                    "exit_rate"]].sort_values(["county_fips", "year", "unit", "store_group"])
    cy.to_csv(OUT / "county_year.csv.gz", index=False)
    log["county_year_rows"] = len(cy)
    log["county_year_counties"] = int(cy["county_fips"].nunique())

    # tract (wide)
    st = ss[ss["tract_geoid"].notna()]
    t_all = flows(st[st["store_group"].isin(FIXED)], ["tract_geoid"]).rename(
        columns={"stock_jan1": "stores_stock_jan1", "entries": "stores_entries", "exits": "stores_exits"})
    t_lg = flows(st[st["store_group"] == "Large store"], ["tract_geoid"])[["tract_geoid", "year", "stock_jan1"]] \
        .rename(columns={"stock_jan1": "large_stores_stock_jan1"})
    t_cv = flows(st[st["store_group"] == "Convenience"], ["tract_geoid"])[["tract_geoid", "year", "stock_jan1"]] \
        .rename(columns={"stock_jan1": "convenience_stock_jan1"})
    t_lo = flows(ls[ls["tract_geoid"].notna()], ["tract_geoid"]).rename(
        columns={"stock_jan1": "locations_stock_jan1", "entries": "locations_entries", "exits": "locations_exits"})
    ty = t_all.merge(t_lo, on=["tract_geoid", "year"], how="outer") \
        .merge(t_lg, on=["tract_geoid", "year"], how="left").merge(t_cv, on=["tract_geoid", "year"], how="left")
    for c in ty.columns.drop(["tract_geoid", "year"]):
        ty[c] = ty[c].astype("Int64")
        if not c.endswith("exits"):
            ty[c] = ty[c].fillna(0)
        else:
            ty.loc[ty["year"] <= LAST_EXIT_YEAR, c] = ty.loc[ty["year"] <= LAST_EXIT_YEAR, c].fillna(0)
    keep = ty.drop(columns=["tract_geoid", "year"]).fillna(0).sum(axis=1) > 0
    ty = ty[keep].sort_values(["tract_geoid", "year"])
    ty = ty[["tract_geoid", "year", "stores_stock_jan1", "stores_entries", "stores_exits", "locations_stock_jan1",
             "locations_entries", "locations_exits", "large_stores_stock_jan1", "convenience_stock_jan1"]]
    ty.to_csv(OUT / "tract_year.csv.gz", index=False)
    log["tract_year_rows"] = len(ty)
    log["tract_year_tracts"] = int(ty["tract_geoid"].nunique())
    (INT / "panels_log.json").write_text(json.dumps(log, indent=2))
    print(json.dumps(log, indent=2))


if __name__ == "__main__":
    main()
