#!/usr/bin/env python3
"""06_qa.py — quality report and stats file.

Writes data/processed/qa_report.txt (read it before trusting anything) and
data/processed/stats.json (every number quoted in README, codebook and figure
captions). Exits 1 if any hard check fails.

Usage:  python code/06_qa.py
"""
import json
import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
INT = ROOT / "data" / "interim"
OUT = ROOT / "data" / "processed"
PAPER = dict(records=690208, store_spells=657298, location_spells=478117, locations=424118)  # Retailer Churn v0.1.0
STATE_FIPS = {"AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08", "CT": "09", "DE": "10",
              "DC": "11", "FL": "12", "GA": "13", "HI": "15", "ID": "16", "IL": "17", "IN": "18", "IA": "19",
              "KS": "20", "KY": "21", "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27",
              "MS": "28", "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33", "NJ": "34", "NM": "35",
              "NY": "36", "NC": "37", "ND": "38", "OH": "39", "OK": "40", "OR": "41", "PA": "42", "RI": "44",
              "SC": "45", "SD": "46", "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53",
              "WV": "54", "WI": "55", "WY": "56", "GU": "66", "VI": "78"}
lines, fails = [], []


def say(s=""):
    lines.append(s)


def check(ok, label):
    say(("PASS  " if ok else "FAIL  ") + label)
    if not ok:
        fails.append(label)


def n(x):
    return f"{x:,}"


def main():
    cl = json.loads((INT / "clean_log.json").read_text())
    gl = json.loads((INT / "geo_log.json").read_text())
    sl = json.loads((INT / "spells_log.json").read_text())
    pl = json.loads((INT / "panels_log.json").read_text())
    a = pd.read_parquet(INT / "authorizations.parquet")
    ss = pd.read_parquet(INT / "store_spells.parquet")
    ls = pd.read_parquet(INT / "location_spells.parquet")
    nat = pd.read_csv(OUT / "national_year.csv")
    cy = pd.read_csv(OUT / "county_year.csv.gz", dtype={"county_fips": str})
    ty = pd.read_csv(OUT / "tract_year.csv.gz", dtype={"tract_geoid": str})
    gap = sl["GAP_DAYS"]

    say("QA REPORT: The SNAP Retailer Spell Panel, 2005-2025 (v1.0.0)")
    say(f"continuity window (V1): {gap} days; nearest-tract tolerance (V2): {gl['NEAREST_M']} m")
    say()
    say("1. ROW COUNTS")
    for k, v in [("FNS records (raw)", cl["records_raw"]), ("FNS Record IDs", cl["record_ids_raw"]),
                 ("authorization rows (part1 + part2)", len(a)),
                 ("  end date before authorization date (kept, no spell)", cl["records_end_before_auth"]),
                 ("  outside 50 states + DC (GU, VI)", cl["records_outside_50_states_dc"]),
                 ("  farmers' markets + delivery routes", cl["records_not_fixed_location"]),
                 ("store spells", len(ss)), ("locations (fixed-location addresses)", sl["locations"]),
                 ("location spells", len(ls)), ("county-year rows", len(cy)), ("tract-year rows", len(ty))]:
        say(f"   {k:<55}{n(v):>12}")
    check(len(a) == cl["records_raw"], "every FNS record is in the authorization files (nothing dropped)")
    check(a["record_id"].nunique() == cl["record_ids_raw"], "every Record ID is present")
    ok = ~a["end_before_auth"]
    check(a.loc[ok, "store_spell_id"].notna().all() and a.loc[~ok, "store_spell_id"].isna().all(),
          "every valid record has exactly one store spell; invalid-date records have none")
    lk = ok & a["fixed_location"]
    check(a.loc[lk, "location_spell_id"].notna().all() and a.loc[~lk, "location_spell_id"].isna().all(),
          "every valid fixed-location record has a location spell; others have none")
    check(set(a["store_spell_id"].dropna()) == set(ss["store_spell_id"]), "store spell IDs match between files")
    check(set(a["location_spell_id"].dropna()) == set(ls["location_spell_id"]), "location spell IDs match between files")
    check(ss.groupby("store_spell_id").size().max() == 1 and ls.groupby("location_spell_id").size().max() == 1,
          "spell IDs unique")
    check(ss["n_records"].sum() == ok.sum(), "store spells account for every valid record")
    check(ls["n_records"].sum() == lk.sum(), "location spells account for every valid fixed-location record")

    say()
    say("2. AGREEMENT WITH RETAILER CHURN AND FOOD ACCESS v0.1.0 (doi:10.5281/zenodo.22884651)")
    say("   restricted to 50 states + DC, fixed-location retailers, valid dates, 365-day window")
    for k in PAPER:
        mine = sl[f"paper_sample_{k}"]
        say(f"   {k:<20} this release {n(mine):>10}   paper {n(PAPER[k]):>10}")
        if gap == 365:
            check(mine == PAPER[k], f"{k} reproduce the working paper exactly")

    say()
    say("3. GEOCODING")
    gm = a["geo_method"].value_counts()
    tot = len(a)
    for m in ["point", "point_nearest", "county_name", "county_zip", "none"]:
        say(f"   {m:<16}{n(int(gm.get(m, 0))):>10}  {100 * gm.get(m, 0) / tot:6.2f}%")
    cc = a["coord_check"].value_counts()
    say("   coordinate check: " + ", ".join(f"{k} {n(int(v))}" for k, v in cc.items()))
    say(f"   tracts in Census file: {n(gl['tracts'])}; counties {n(gl['counties'])}; "
        f"tracts with any SNAP retailer: {n(int(a['tract_geoid'].nunique()))}")
    tract_rate = a["tract_geoid"].notna().mean()
    county_rate = a["county_fips"].notna().mean()
    check(county_rate == 1.0, f"county assigned for {100 * county_rate:.3f}% of records")
    check(tract_rate > 0.99, f"tract assigned for {100 * tract_rate:.3f}% of records (> 99%)")
    t = a.dropna(subset=["tract_geoid"])
    check((t["tract_geoid"].str.len() == 11).all() and (t["tract_geoid"].str[:5] == t["county_fips"]).all(),
          "tract GEOIDs are 11 digits and nest in the assigned county")
    check((a["county_fips"].str[:2] == a["state"].map(STATE_FIPS)).all(), "assigned county lies in the record's state")
    dis = int((a["county_agrees_fns"] == False).sum())  # noqa: E712
    cmp_ = int(a["county_agrees_fns"].notna().sum())
    say(f"   point county differs from the FNS county field: {n(dis)} of {n(cmp_)} compared ({100 * dis / cmp_:.2f}%)")
    say("     (mostly stores near county lines, Virginia independent cities, and FNS county-field errors;")
    say("      the point-based county is used)")
    shared = int((a["coord_shared_locations"] >= 10).sum())
    say(f"   records whose exact coordinates are shared by >= 10 distinct addresses: {n(shared)}")

    say()
    say("4. DATA FEATURES THAT SHAPE INTERPRETATION")
    say(f"   1 Jan 1930 placeholder authorization date: {n(cl['records_auth_placeholder_1930'])} records")
    say(f"   End Dates shared by >= 1,000 records (administrative batch dates): {len(cl['batch_end_dates'])}; "
        f"records ending on one: {n(cl['records_end_on_batch_date'])}")
    say(f"   ZIP codes restored to 5 digits (leading zero dropped in source): {n(cl['zip_codes_restored_leading_zero'])}")
    say(f"   records without a street address (keyed by Record ID): {n(cl['records_without_street_address'])}")
    say(f"   Record IDs with more than one store spell: {n(int((ss.groupby('record_id').size() > 1).sum()))}")
    say(f"   store spells open at 31 Dec 2025: {n(int(ss['open_at_file_end'].sum()))}")
    say(f"   location spells open at 31 Dec 2025: {n(int(ls['open_at_file_end'].sum()))}")

    say()
    say("5. CONSISTENCY AND RANGE CHECKS")
    check((ss["end_date"].isna() | (ss["end_date"] >= ss["start_date"])).all(), "store spells: end >= start")
    check((ls["end_date"].isna() | (ls["end_date"] >= ls["start_date"])).all(), "location spells: end >= start")
    s2 = ss.sort_values(["record_id", "start_date"])
    prev_end = s2.groupby("record_id")["end_date"].shift()
    gapd = (s2["start_date"] - prev_end).dt.days
    check((gapd.dropna() > gap).all(), f"consecutive store spells of a Record ID are > {gap} days apart")
    l2 = ls.sort_values(["location_id", "start_date"])
    gapl = (l2["start_date"] - l2.groupby("location_id")["end_date"].shift()).dt.days
    check((gapl.dropna() > gap).all(), f"consecutive location spells of an address are > {gap} days apart")
    for unit, grp in [("store", "All fixed-location"), ("location", "All fixed-location")]:
        t = nat[(nat["coverage"] == "all") & (nat["unit"] == unit) & (nat["store_group"] == grp)].sort_values("year")
        ident = (t["stock_jan1"].shift(-1) - (t["stock_jan1"] + t["entries"] - t["exits"])).iloc[:-2]
        check((ident == 0).all(), f"national {unit}s: stock(y+1) = stock(y) + entries - exits, every year")
        say(f"   {unit}: exit rate {t['exit_rate'].min():.3f}-{t['exit_rate'].max():.3f}; "
            f"entry rate {t['entry_rate'].min():.3f}-{t['entry_rate'].max():.3f}; "
            f"stock {n(int(t['stock_jan1'].min()))}-{n(int(t['stock_jan1'].max()))}")
        check(t["exit_rate"].dropna().between(0, 0.5).all() and t["entry_rate"].between(0, 0.5).all(),
              f"national {unit} rates within [0, 0.5]")
    cs = cy[(cy["unit"] == "store") & (cy["store_group"] == "All fixed-location")].groupby("year")["stock_jan1"].sum()
    ns = nat[(nat["coverage"] == "all") & (nat["unit"] == "store") & (nat["store_group"] == "All fixed-location")] \
        .set_index("year")["stock_jan1"]
    check((cs == ns).all(), "county-year store stock sums to the national stock")
    tl = ty.groupby("year")["locations_stock_jan1"].sum()
    nl = nat[(nat["coverage"] == "all") & (nat["unit"] == "location")].set_index("year")["stock_jan1"]
    share = (tl / nl).min()
    say(f"   tract-year location stock / national: at least {100 * share:.2f}% every year")
    check(share > 0.99, "tract-year panel covers > 99% of the national location stock")

    say()
    say("6. NAMED SPOT CHECKS (look each up by hand: V4)")
    say("   Source: FNS historical CSV (filter on Record ID); for open records the live Retailer Locator")
    say("   https://www.fns.usda.gov/snap/retailer-locator ; tracts: https://geocoding.geo.census.gov")
    picks = [
        (1022007, "easy: open Super Store, Tennessee (Kroger 419)"),
        (1004135, "closed convenience store, Rutherford County TN (Murfreesboro)"),
        (1000667, "hard: three authorizations, same Record ID, two spells"),
        (225857, "1930 placeholder authorization date"),
        (1526890, "record ending on an administrative batch date"),
        (737262, "coordinates recorded as 0, 0 -> county from FNS name, no tract"),
        (1074909, "point county differs from the FNS county field"),
    ]
    rng = np.random.default_rng(20261011)
    rnd = rng.choice(a.loc[a["in_50_states_dc"], "record_id"].unique(), 3, replace=False)
    picks += [(int(x), "random (seed 20261011)") for x in rnd]
    gu = a.loc[(a["state"] == "GU") & (a["geo_method"] == "point"), "record_id"].iloc[0]
    picks.append((int(gu), "territory: Guam"))
    for rid, why in picks:
        say(f"   -- {why}: Record ID {rid}")
        rec = a[a["record_id"] == rid].sort_values("authorization_date")
        for _, x in rec.iterrows():
            end = x["end_date"].date() if pd.notna(x["end_date"]) else "open"
            say(f"      {x['store_name'][:32]:<33}{x['store_type'][:22]:<23}{x['city'][:16]:<17}{x['state']} "
                f"auth {x['authorization_date'].date()} -> {end}")
        x = rec.iloc[0]
        say(f"      county {x['county_fips']} (FNS: {x['county_fns']}), tract {x['tract_geoid']}, "
            f"geo {x['geo_method']}, coords {x['latitude']}, {x['longitude']}")
        say(f"      store spells: {', '.join(rec['store_spell_id'].dropna().unique())}")
    say("   -- location succession: 2080 Valentine Ave, Bronx NY 10457")
    lid = ls.loc[ls["location_key"] == "2080|VALENTINE AVE|10457", "location_id"].iloc[0]
    for _, x in a[a["location_id"] == lid].sort_values("authorization_date").iterrows():
        end = x["end_date"].date() if pd.notna(x["end_date"]) else "open"
        say(f"      {x['record_id']:<9}{x['store_name'][:34]:<35}{x['authorization_date'].date()} -> {end}  "
            f"{x['location_spell_id']}")

    say()
    say("RESULT: " + ("ALL HARD CHECKS PASS" if not fails else f"{len(fails)} HARD CHECK(S) FAILED"))
    (OUT / "qa_report.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))

    nat50 = nat[(nat["coverage"] == "all") & (nat["store_group"] == "All fixed-location")]
    st = {
        "version": "1.0.0", "gap_days": gap, "nearest_m": gl["NEAREST_M"],
        "records": len(a), "record_ids": int(a["record_id"].nunique()), "store_spells": len(ss),
        "locations": sl["locations"], "location_spells": len(ls),
        "first_auth_year_nonplaceholder": int(a.loc[~a["auth_placeholder_1930"], "authorization_date"].dt.year.min()),
        "states_and_territories": int(a["state"].nunique()),
        "records_outside_50_dc": cl["records_outside_50_states_dc"],
        "records_not_fixed_location": cl["records_not_fixed_location"],
        "records_end_before_auth": cl["records_end_before_auth"],
        "records_placeholder_1930": cl["records_auth_placeholder_1930"],
        "batch_end_dates": len(cl["batch_end_dates"]), "records_end_on_batch_date": cl["records_end_on_batch_date"],
        "zip_restored": cl["zip_codes_restored_leading_zero"], "coords_zero": cl["coords_zero"],
        "geo_method": {k: int(v) for k, v in gm.items()}, "pct_tract": round(100 * tract_rate, 2),
        "pct_county": round(100 * county_rate, 2), "county_disagree": dis, "county_compared": cmp_,
        "tracts_with_retailer": int(a["tract_geoid"].nunique()), "counties_with_retailer": int(a["county_fips"].nunique()),
        "store_spells_open": int(ss["open_at_file_end"].sum()), "location_spells_open": int(ls["open_at_file_end"].sum()),
        "rids_multi_spell": int((ss.groupby("record_id").size() > 1).sum()),
        "store_exit_rate_mean_2006_2024": round(float(nat50[nat50["unit"] == "store"]["exits"].sum() /
                                                      nat50[(nat50["unit"] == "store") & (nat50["year"] <= 2024)]["stock_jan1"].sum()), 4),
        "location_exit_rate_mean_2006_2024": round(float(nat50[nat50["unit"] == "location"]["exits"].sum() /
                                                         nat50[(nat50["unit"] == "location") & (nat50["year"] <= 2024)]["stock_jan1"].sum()), 4),
        "stock_2025_stores": int(nat50[(nat50["unit"] == "store") & (nat50["year"] == 2025)]["stock_jan1"].iloc[0]),
        "stock_2025_locations": int(nat50[(nat50["unit"] == "location") & (nat50["year"] == 2025)]["stock_jan1"].iloc[0]),
        "county_year_rows": len(cy), "tract_year_rows": len(ty), "tract_year_tracts": pl["tract_year_tracts"],
        "paper_reproduced": all(sl[f"paper_sample_{k}"] == PAPER[k] for k in PAPER),
        "hard_checks_failed": len(fails),
    }
    (OUT / "stats.json").write_text(json.dumps(st, indent=2))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
