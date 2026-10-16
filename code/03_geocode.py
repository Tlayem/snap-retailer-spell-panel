#!/usr/bin/env python3
"""03_geocode.py — assign 2020 census tract and county to every authorization record.

Method, in order (column `geo_method`):
  point           FNS coordinates fall inside a 2020 census tract in the record's own state
  point_nearest   FNS coordinates fall outside every tract (generalized shoreline, water)
                  but within NEAREST_M metres of a tract in the record's own state
  county_name     coordinates missing, zero, outside the record's state, or beyond
                  NEAREST_M: county assigned by matching the FNS county name to 2020
                  county names within the state (no tract)
  county_zip      county name did not match: county = the most common point-geocoded
                  county among records with the same state and ZIP5 (no tract)
  none            nothing worked

Guam and the U.S. Virgin Islands are not in the Census nationwide tract file; their
records are assigned county-equivalents by name (Guam 66010; St. Croix 78010,
St. John 78020, St. Thomas 78030).

`county_agrees_fns` compares the point-based county with the county named by FNS
(where the FNS name matches a 2020 county); disagreement marks either a coordinate
or a county-field error and is left for users to judge.

Reads data/interim/records_clean.parquet and data/raw/cb_2020_us_tract_500k/.
Writes data/interim/records_geo.parquet and data/interim/geo_log.json.
"""
import json
import pathlib
import re
import unicodedata

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
INT = ROOT / "data" / "interim"
SHP = ROOT / "data" / "raw" / "cb_2020_us_tract_500k" / "cb_2020_us_tract_500k.shp"
NEAREST_M = 500  # author's ruling V2

ISLAND_AREAS = {("GU", "GUAM"): "66010", ("VI", "STCROIX"): "78010", ("VI", "STJOHN"): "78020",
                ("VI", "STTHOMAS"): "78030"}
# FNS spellings that differ from Census names (same list as Retailer Churn and Food Access v0.1.0)
ALIAS = {("DC", "DISTOFCOLUMBIA"): "11001", ("LA", "STJOHNBAPTIST"): "22095", ("KY", "MUHLENBURG"): "21177",
         ("MS", "CHIKASAW"): "28017", ("AK", "FAIRBANKSNOSTAR"): "02090", ("MO", "SAINTEGENEVIEVE"): "29186",
         ("AK", "SEFAIRBANKS"): "02240", ("TX", "BRISCO"): "48045", ("VA", "BEDFORDCITY"): "51019"}


def norm_county(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.upper().replace("&", "AND")
    s = re.sub(r"[.'`,-]", " ", s)
    s = re.sub(r"\bSAINT\b", "ST", s)
    s = re.sub(r"\bSTE\b", "ST", s)
    s = re.sub(r"\b(COUNTY|PARISH|BOROUGH|CENSUS AREA|CITY AND BOROUGH|MUNICIPALITY|PLANNING REGION)\b", " ", s)
    return re.sub(r"\s+", "", s)


def county_crosswalk(tr):
    cty = tr[["STUSPS", "county_fips", "NAMELSADCO"]].drop_duplicates("county_fips")
    prim = pd.DataFrame({"state": cty["STUSPS"], "ckey": cty["NAMELSADCO"].map(norm_county), "fips": cty["county_fips"]})
    # Virginia independent cities without the word CITY, only where no county has that name
    sec = prim.assign(ckey=prim["ckey"].str.replace(r"CITY$", "", regex=True))
    sec = sec[~sec.set_index(["state", "ckey"]).index.isin(prim.set_index(["state", "ckey"]).index)]
    sec = sec[~sec.duplicated(["state", "ckey"], keep=False)]
    extra = pd.DataFrame([(k[0], k[1], v) for k, v in {**ALIAS, **ISLAND_AREAS}.items()],
                         columns=["state", "ckey", "fips"])
    return pd.concat([prim, sec, extra]).drop_duplicates(["state", "ckey"])


def main():
    log = {"NEAREST_M": NEAREST_M}
    r = pd.read_parquet(INT / "records_clean.parquet",
                        columns=["state", "zip5", "county_fns", "latitude_fns", "longitude_fns", "coord_status"])
    tr = gpd.read_file(SHP)[["GEOID", "STUSPS", "NAMELSADCO", "geometry"]]
    tr["county_fips"] = tr["GEOID"].str[:5]
    log["tracts"] = len(tr)
    log["tract_states"] = int(tr["STUSPS"].nunique())
    log["counties"] = int(tr["county_fips"].nunique())

    # ---- point in polygon on unique coordinate pairs
    has = r["coord_status"] == "present"
    pts = r.loc[has, ["latitude_fns", "longitude_fns"]].drop_duplicates().reset_index(drop=True)
    g = gpd.GeoDataFrame(pts, geometry=gpd.points_from_xy(pts["longitude_fns"], pts["latitude_fns"]), crs="EPSG:4326")
    g = g.to_crs(tr.crs)
    j = gpd.sjoin(g, tr, how="left", predicate="within")
    j = j[~j.index.duplicated()]  # a point on a shared boundary: keep the first tract
    pts["tract_geoid"] = j["GEOID"].values
    pts["tract_state"] = j["STUSPS"].values
    pts["method"] = np.where(pts["tract_geoid"].notna(), "point", None)
    log["coord_pairs"] = len(pts)
    log["coord_pairs_inside_tract"] = int(pts["tract_geoid"].notna().sum())

    # ---- nearest tract within NEAREST_M for the misses (equal-area metres, per region)
    miss = pts["tract_geoid"].isna()
    regions = [("conus", "EPSG:5070", (-125, 24, -66, 50)), ("alaska", "EPSG:3338", (-180, 50, -129, 72)),
               ("hawaii", "EPSG:32604", (-161, 18, -154, 23)), ("prvi", "EPSG:32161", (-68, 17, -64, 19)),
               ("pacific", "EPSG:32655", (140, 10, 150, 22))]
    for name, crs, (x0, y0, x1, y1) in regions:
        sel = miss & pts["longitude_fns"].between(x0, x1) & pts["latitude_fns"].between(y0, y1)
        if not sel.any():
            continue
        gp = gpd.GeoDataFrame(pts.loc[sel, []], geometry=gpd.points_from_xy(
            pts.loc[sel, "longitude_fns"], pts.loc[sel, "latitude_fns"]), crs="EPSG:4326").to_crs(crs)
        tt = tr.cx[x0:x1, y0:y1].to_crs(crs)
        if tt.empty:
            continue
        n = gpd.sjoin_nearest(gp, tt, how="left", max_distance=NEAREST_M, distance_col="dist")
        n = n[~n.index.duplicated()]
        found = n["GEOID"].notna()
        idx = n.index[found]
        pts.loc[idx, "tract_geoid"] = n.loc[found, "GEOID"].values
        pts.loc[idx, "tract_state"] = n.loc[found, "STUSPS"].values
        pts.loc[idx, "method"] = "point_nearest"
    log["coord_pairs_nearest_tract"] = int((pts["method"] == "point_nearest").sum())

    out = r.merge(pts, on=["latitude_fns", "longitude_fns"], how="left")
    assert len(out) == len(r)
    out.index = r.index
    wrong_state = out["tract_geoid"].notna() & (out["tract_state"] != out["state"])
    log["records_coord_in_other_state"] = int(wrong_state.sum())
    log["records_coord_in_other_state_by_state"] = out.loc[wrong_state, "state"].value_counts().head(15).to_dict()
    out.loc[wrong_state, ["tract_geoid", "method"]] = [None, None]
    log["records_coord_no_tract_within_tolerance"] = int((has & out["method"].isna() & ~wrong_state).sum())
    out["coord_check"] = np.select(
        [~has, wrong_state, out["method"] == "point", out["method"] == "point_nearest"],
        [out["coord_status"], "other_state", "inside_tract", "near_tract"], "no_tract_nearby")
    out["county_fips"] = out["tract_geoid"].str[:5]

    # ---- FNS county name -> 2020 county (used for agreement and fallback)
    xw = county_crosswalk(tr)
    out["ckey"] = out["county_fns"].fillna("").map(norm_county)
    name_fips = out[["state", "ckey"]].merge(xw, on=["state", "ckey"], how="left")["fips"].values
    out["fips_from_name"] = name_fips
    log["records_fns_county_name_matched"] = int(pd.notna(name_fips).sum())

    both = out["county_fips"].notna() & out["fips_from_name"].notna()
    out["county_agrees_fns"] = pd.Series(pd.NA, index=out.index, dtype="boolean")
    out.loc[both, "county_agrees_fns"] = out.loc[both, "county_fips"] == out.loc[both, "fips_from_name"]
    log["records_point_county_compared"] = int(both.sum())
    log["records_point_county_disagrees"] = int((out["county_agrees_fns"] == False).sum())  # noqa: E712

    need = out["county_fips"].isna() & out["fips_from_name"].notna()
    out.loc[need, "county_fips"] = out.loc[need, "fips_from_name"]
    out.loc[need, "method"] = "county_name"
    zmode = out[out["method"].isin(["point", "point_nearest"])].groupby(["state", "zip5"])["county_fips"] \
        .agg(lambda s: s.value_counts().index[0])
    need = out["county_fips"].isna()
    imp = pd.Series(list(zip(out.loc[need, "state"], out.loc[need, "zip5"])), index=out.index[need]).map(zmode)
    out.loc[need, "county_fips"] = imp
    out.loc[need & out["county_fips"].notna(), "method"] = "county_zip"
    out["method"] = out["method"].fillna("none")
    log["records_by_geo_method"] = out["method"].value_counts().to_dict()
    log["records_with_tract"] = int(out["tract_geoid"].notna().sum())
    log["records_with_county"] = int(out["county_fips"].notna().sum())
    unm = out[out["method"] == "none"].groupby(["state", "county_fns"]).size().sort_values(ascending=False)
    log["unassigned_by_state_county"] = {f"{a}|{b}": int(v) for (a, b), v in unm.head(20).items()}

    res = pd.DataFrame({
        "county_fips": out["county_fips"], "tract_geoid": out["tract_geoid"], "geo_method": out["method"],
        "coord_check": out["coord_check"], "county_agrees_fns": out["county_agrees_fns"],
        "latitude": r["latitude_fns"], "longitude": r["longitude_fns"],
    })
    res.to_parquet(INT / "records_geo.parquet", index=False)
    (INT / "geo_log.json").write_text(json.dumps(log, indent=2))
    print(json.dumps(log, indent=2))


if __name__ == "__main__":
    main()
