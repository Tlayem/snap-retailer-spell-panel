#!/usr/bin/env python3
"""08_docs.py — README, LIMITATIONS, CITATION.cff and .zenodo.json from stats.json and AUTHORS.json.

Every number in these files comes from data/processed/stats.json, so text cannot drift
from data. Draft banner unless --final.
Usage:  python code/08_docs.py [--final]
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
FINAL = "--final" in sys.argv
S = json.loads((ROOT / "data" / "processed" / "stats.json").read_text())
A = json.loads((ROOT / "AUTHORS.json").read_text())["authors"][0]
# DOI: pass --doi 10.5281/zenodo.NNN once Zenodo has minted it; omitted until then
DOI = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--doi=")), "")
DOI_URL = f"https://doi.org/{DOI}" if DOI else ""
VERSION = S["version"]
TITLE = "The SNAP Retailer Spell Panel, 2005–2025"
DATE = "2026-10-11"
RELATED = "10.5281/zenodo.22884650"  # Retailer Churn and Food Access (concept DOI)


def n(x):
    return f"{x:,}"


g = S["geo_method"]
banner = "" if FINAL else "> **DRAFT — not for citation. Awaiting author verification.**\n\n"
status = f"**Version {VERSION}{'' if FINAL else ' DRAFT'} — October 2026.**" + (f" DOI: [{DOI}]({DOI_URL})" if DOI else "")

readme = f"""{banner}# {TITLE}

{status}

A cleaned, geocoded, spell-level panel of every retailer authorized to accept SNAP (food stamp) benefits in the
United States at any time from 2005 to 2025. It is built from USDA's SNAP Retailer Locator historical file.

The source lists one row per authorization. This dataset turns that list into three things:

- **Store spells:** when each store entered and left SNAP.
- **Location spells:** when each street address had, or lost, SNAP retail of any kind.
- **Geography:** every record carries a 2020 census tract and county, so the panel joins directly to Census, ACS and
  USDA Food Access Research Atlas data.

![Stock and exit rates](docs/figures/overview.png)

## Contents

| File | Rows | One row per |
|---|---:|---|
| `data/processed/authorizations_part1.csv.gz`, `_part2`, `_part3` | {n(S['records'])} | FNS authorization record (every record in the source; nothing dropped). Split by Record ID into three files for upload limits; stack them to use. |
| `data/processed/store_spells.csv.gz` | {n(S['store_spells'])} | store spell ({n(S['record_ids'])} stores) |
| `data/processed/location_spells.csv.gz` | {n(S['location_spells'])} | address spell ({n(S['locations'])} addresses) |
| `data/processed/national_year.csv` | | year × store group: stock on 1 January, entries, exits, rates |
| `data/processed/county_year.csv.gz` | {n(S['county_year_rows'])} | county × year × store group |
| `data/processed/tract_year.csv.gz` | {n(S['tract_year_rows'])} | census tract × year ({n(S['tract_year_tracts'])} tracts) |
| `data/processed/qa_report.txt`, `stats.json` | | quality report; every number in this README |

Every column is defined in [`docs/CODEBOOK.md`](docs/CODEBOOK.md). Read [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md)
before using the data.

## What was done

- **Cleaned.**
  - All {n(S['records'])} records from all {S['states_and_territories']} states and territories are kept. Problems are
    flagged, not deleted.
  - ZIP codes that had lost their leading zero ({n(S['zip_restored'])} records) are restored.
  - Coordinates of (0, 0) ({n(S['coords_zero'])} records) are set to missing.
  - Flags mark FNS's 1930 placeholder start dates ({n(S['records_placeholder_1930'])}), end dates earlier than start
    dates ({n(S['records_end_before_auth'])}), and {S['batch_end_dates']} administrative batch end dates.
- **Geocoded.**
  - {n(g.get('point', 0) + g.get('point_nearest', 0))} records ({S['pct_tract']}%) were placed in a 2020 census tract
    from their FNS coordinates. Coordinates outside the record's own state were rejected.
  - The remaining records got a county from the FNS county name or ZIP code, so county coverage is {S['pct_county']}%.
  - The point-based county differs from the FNS county field for {n(S['county_disagree'])} records; each such record
    is flagged.
- **Spell-constructed.**
  - Authorizations of the same store, and of the same address, are merged into spells when a gap is {S['gap_days']}
    days or less.
  - Restricted to the 50 states and DC and to fixed-location retailers, the spells reproduce exactly those in
    *Retailer Churn and Food Access* (Adesiyan 2026, doi:10.5281/zenodo.22884651).

In 2006–2024 stores left SNAP at an average of {100 * S['store_exit_rate_mean_2006_2024']:.1f}% a year. Addresses lost
all SNAP retail at {100 * S['location_exit_rate_mean_2006_2024']:.1f}% a year. On 1 January 2025,
{n(S['stock_2025_stores'])} fixed-location stores were active.

## Rebuild it

Python 3.11 with pandas, numpy, pyarrow, geopandas (shapely, pyogrio) and matplotlib.

```
python code/01_fetch.py        # downloads or checks the two inputs and logs SHA-256 to data/raw/PROVENANCE.txt
python code/02_clean.py        # cleaned authorization records
python code/03_geocode.py      # 2020 tract and county for every record
python code/04_spells.py       # store and location spells; optional argument = continuity window in days (default 365)
python code/05_panels.py       # national, county and tract annual panels
python code/06_qa.py           # data/processed/qa_report.txt and stats.json; exits 1 on a failed check
python code/07_figure.py       # docs/figures/overview.png
python code/08_docs.py         # this README, LIMITATIONS, CITATION.cff, .zenodo.json
```

USDA and Census servers sometimes refuse scripted downloads. If `01_fetch.py` stops, save the file from the landing
page below into `data/raw/` under the name it prints. The script then checks the hash.

## Sources

| Source | Vintage | Landing page |
|---|---|---|
| USDA Food and Nutrition Service, SNAP Retailer Locator historical data 2005–2025 | current to 31 Dec 2025 (page updated 19 Feb 2026) | https://www.fns.usda.gov/snap/retailer-locator/data |
| U.S. Census Bureau, 2020 cartographic boundary file, census tracts, 1:500,000 (`cb_2020_us_tract_500k`) | 2020 tracts (file dated May 2023) | https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.2020.html |

Both are U.S. government works in the public domain. File hashes are in `data/raw/PROVENANCE.txt`. The raw inputs are
not redistributed here; `01_fetch.py` fetches them.

## License and citation

Code is under the [MIT License](LICENSE). Data and documentation are under [CC BY 4.0](LICENSE-DATA); please also
credit USDA FNS and the U.S. Census Bureau as sources.

Cite as: Adesiyan, T. F. (2026). *{TITLE}* (Version {VERSION}) [Data set]. Zenodo.{(' ' + DOI_URL) if DOI else ''}

Related work: Adesiyan, T. F. (2026). *Retailer Churn and Food Access* (Version 0.1.0). Working paper. Zenodo.
https://doi.org/10.5281/zenodo.22884651

Maintainer: {A['correspondence_name']}, {A['affiliation']} · {A['email']} · ORCID {A['orcid']}
"""

limitations = f"""{banner}# Limitations

1. **An authorization is not a store being open.** The source records SNAP authorization, not whether a business is
   trading. A store can keep trading after leaving SNAP, and a closed store's authorization can linger until FNS
   removes it. Every exit here is an exit from SNAP retail.

2. **Some end dates are administrative.**
   - {S['batch_end_dates']} end dates are each shared by 1,000 or more records nationally, and
     {n(S['records_end_on_batch_date'])} records end on one of them (`end_on_batch_date`).
   - These look like batch actions, such as reauthorization non-response. They date when FNS recorded the exit, not
     when trading stopped, so annual exit counts are lumpy.

3. **The continuity window is a judgment.**
   - Gaps of {S['gap_days']} days or less are treated as continuous, for stores and for addresses.
   - Spells ending within {S['gap_days']} days of 31 Dec 2025 may still be continued by a re-authorization not yet
     observed (`end_within_window_of_file_end`), so annual exits stop at 2024.
   - `04_spells.py` rebuilds the spells at any window.

4. **Coverage starts in 2005.**
   - The file lists retailers authorized at any time in 2005–2025. Stores that left before 2005 are absent, and earlier
     spells of a store active in 2005 are not seen.
   - {n(S['records_placeholder_1930'])} records carry a 1 January 1930 placeholder authorization date; their true start
     is unknown (`auth_placeholder_1930`).

5. **Address matching is literal.**
   - Locations are keyed on street number, a lightly standardized street name and ZIP5. Different spellings of one
     address split it into two locations, which overstates location turnover.
   - Unit numbers are ignored, so stores in one strip-mall address share a location.
   - Records with no street address are keyed by Record ID.

6. **Geocodes are FNS's coordinates.**
   - Tracts come from the coordinates FNS publishes, not from re-geocoding the addresses.
   - Some coordinates are ZIP or city centroids: `coord_shared_locations` counts the distinct addresses at the exact
     same point.
   - The tract file is generalized (1:500,000), so points on shorelines were matched to the nearest tract within
     {S['nearest_m']} m.
   - {n(S['county_disagree'])} records ({100 * S['county_disagree'] / S['county_compared']:.2f}%) fall in a different
     county from the one FNS names. These are mostly stores near county lines, Virginia independent cities, and errors
     in the FNS county field. Both values are kept.

7. **2020 geography for every year.** All records are placed in 2020 tracts and counties, whatever their year. This
   gives one consistent geography, but users linking to data on 2010 tracts need a crosswalk.

8. **Store type is one value per Record ID** and can lag a change in format. Grouping the 17 FNS store types into
   five fixed-location groups is a judgment.

9. **Farmers' markets and delivery routes** keep their store spells but have no location spells, because their
   address is a market site or a route base.
"""

cff = f"""cff-version: 1.2.0
message: "If you use this dataset, please cite it as below."
type: dataset
title: "{TITLE}"
version: {VERSION}
date-released: "{DATE}"
{('doi: "' + DOI + '"' + chr(10)) if DOI else ''}license: CC-BY-4.0
repository-code: "https://github.com/Tlayem/snap-retailer-spell-panel"
authors:
  - family-names: "{A['family']}"
    given-names: "{A['given']}"
    orcid: "https://orcid.org/{A['orcid']}"
    affiliation: "{A['affiliation']}"
    email: "{A['email']}"
keywords: [SNAP, food retail, food access, retailer entry and exit, spell data, census tracts, panel data]
references:
  - type: report
    title: "Retailer Churn and Food Access"
    authors:
      - family-names: "{A['family']}"
        given-names: "{A['given']}"
    year: 2026
    doi: "10.5281/zenodo.22884651"
"""

zen = {
    "title": TITLE,
    "upload_type": "dataset",
    "version": VERSION,
    "description": (
        "<p>A cleaned, geocoded, spell-level panel of every retailer authorized to accept SNAP benefits in the "
        f"United States at any time from 2005 to 2025, built from the USDA FNS SNAP Retailer Locator historical "
        f"file (current to 31 Dec 2025). It contains {n(S['records'])} authorization records, "
        f"{n(S['store_spells'])} store spells, {n(S['location_spells'])} address spells, and annual national, "
        f"county and census-tract panels of retailer stock, entry and exit. {S['pct_tract']}% of records are placed in a "
        f"2020 census tract and every record in a county. Spells merge gaps of {S['gap_days']} days or less and reproduce "
        "those of the working paper Retailer Churn and Food Access (doi:10.5281/zenodo.22884651).</p>"),
    "creators": [{"name": f"{A['family']}, {A['given']}", "affiliation": A["affiliation"], "orcid": A["orcid"]}],
    "license": "cc-by-4.0",
    "keywords": ["SNAP", "food retail", "food access", "retailer entry and exit", "spell data", "census tracts",
                 "panel data", "USDA"],
    "related_identifiers": [{"identifier": RELATED, "relation": "references", "scheme": "doi",
                             "resource_type": "publication-workingpaper"}],
}

(ROOT / "README.md").write_text(readme)
(ROOT / "docs" / "LIMITATIONS.md").write_text(limitations)
(ROOT / "CITATION.cff").write_text(cff)
(ROOT / ".zenodo.json").write_text(json.dumps(zen, indent=2, ensure_ascii=False) + "\n")
print("wrote README.md, docs/LIMITATIONS.md, CITATION.cff, .zenodo.json", "(final)" if FINAL else "(draft)")
