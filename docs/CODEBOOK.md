# Codebook: The SNAP Retailer Spell Panel, 2005–2025 (v1.0.0)

The source is the USDA FNS SNAP Retailer Locator historical data 2005–2025 ("FNS"), current to 31 December 2025.
Geography comes from the U.S. Census Bureau 2020 cartographic boundary file for census tracts ("Census").

- Dates are ISO `YYYY-MM-DD`.
- An empty `end_date` means the authorization or spell was still open on 31 December 2025.
- Booleans are `True`/`False`.
- FIPS codes and GEOIDs are text, so keep their leading zeros: read them as strings.
- All files are UTF-8 CSV, gzip-compressed where named `.gz`.

## Linking the files

```
authorizations ──record_id──────────▶ store_spells (store_spell_id)
       │
       └──location_id / location_spell_id──▶ location_spells
store_spells, location_spells ──county_fips / tract_geoid──▶ county_year, tract_year, any Census-keyed data
```

## authorizations_part1.csv.gz + authorizations_part2.csv.gz — one row per FNS authorization record (every record in the source)

The table is split by Record ID into two files (part 1: Record ID below 998037; part 2: 998037 and above) only to stay under
GitHub's upload limit. Stack them to use: in R `rbind(read.csv(p1), read.csv(p2))`; in pandas `pd.concat([pd.read_csv(p1), pd.read_csv(p2)])`.

| column | definition | source / transformation |
|---|---|---|
| record_id | FNS store identifier | FNS `Record ID`. One store can have several authorization records. |
| store_spell_id | the store spell this record belongs to, `<record_id>-<n>` | built by `04_spells.py`. Empty if `end_before_auth`. |
| location_id | integer ID of the address | from `location_key` (see location_spells). Empty for farmers' markets and delivery routes. |
| location_spell_id | the location spell this record belongs to, `<location_id>-<n>` | built by `04_spells.py` |
| store_name | store name as published | FNS `Store Name`, trimmed |
| store_type | FNS store type (17 values) | FNS `Store Type` |
| store_group | Large store / Grocery / Convenience / Specialty / Other / Farmers' market / Delivery route | mapping in `02_clean.py` (`GROUP`). Ruling V3. |
| street_number, street_name, additional_address, city | address as published | FNS, trimmed |
| state | USPS state or territory code (50 states, DC, GU, VI) | FNS `State` |
| zip5 | 5-digit ZIP code | FNS `Zip Code`. Leading zeros the source dropped are restored. |
| zip4 | ZIP+4 add-on, 4 digits, or empty | FNS `Zip4`, zero-padded |
| county_fns | county name as written by FNS | FNS `County` |
| county_fips | 2020 county FIPS (5 digits) | first five digits of `tract_geoid`. When there is no tract, matched from the FNS county name or the ZIP (see `geo_method`). |
| tract_geoid | 2020 census tract GEOID (11 digits) | point-in-polygon of the FNS coordinates against Census 2020 tracts. Empty when the coordinates are unusable. |
| geo_method | `point`, `point_nearest`, `county_name`, `county_zip` | `point`: inside a tract in the record's state. `point_nearest`: within 500 m of one (ruling V2). `county_name`: county from the FNS name, no tract. `county_zip`: modal county of the ZIP, no tract. |
| county_agrees_fns | the point-based county equals the county named by FNS | empty when either is unavailable |
| latitude, longitude | FNS coordinates (WGS84 decimal degrees) | FNS `Latitude`/`Longitude`. (0, 0) is set to empty. |
| coord_check | `inside_tract`, `near_tract`, `other_state`, `no_tract_nearby`, `zero` | result of checking the coordinates against the record's state |
| coord_shared_locations | number of distinct addresses in the file whose coordinates are exactly these | high values suggest a ZIP or city centroid rather than a rooftop point |
| authorization_date | start of this authorization | FNS `Authorization Date` |
| end_date | end of this authorization; empty if open on 31 Dec 2025 | FNS `End Date` |
| auth_placeholder_1930 | the authorization date is FNS's 1 January 1930 placeholder (the true start is unknown) | flag |
| end_before_auth | the end date precedes the authorization date (source error) | flag. These records enter no spell. |
| end_on_batch_date | the end date is shared by 1,000 or more records nationally (an administrative batch action) | flag |
| in_50_states_dc | the state is one of the 50 states or DC | flag |
| fixed_location | not a farmers' market or delivery route | flag |
| has_street_address | street number and street name both present | flag. If false, the address key falls back to the Record ID. |

## store_spells.csv.gz — one row per store spell

A store spell is one Record ID's continuous SNAP authorization. Authorization records of the same Record ID are merged
when the next one starts within 365 days of the latest end so far (ruling V1). Rebuild at another window with
`python code/04_spells.py <days>`.

| column | definition |
|---|---|
| store_spell_id | `<record_id>-<spell_number>` |
| record_id, spell_number | FNS Record ID; order of the spell within that Record ID (1, 2, …) |
| start_date / end_date | earliest authorization date / latest end date in the spell; empty end date = open on 31 Dec 2025 |
| n_records | authorization records merged into the spell |
| store_name, store_type, store_group, state, zip5, county_fips, tract_geoid, geo_method | as in authorizations. These attributes are constant within a Record ID in the source; QA checks this. |
| location_id | the address of the store (links to location_spells) |
| start_placeholder_1930 | the spell starts on the 1930 placeholder; the true start is before 2005 and unknown |
| end_on_batch_date | the spell's final end date is an administrative batch date |
| open_at_file_end | the spell was open on 31 Dec 2025 (right-censored) |
| end_within_window_of_file_end | the spell ended less than 365 days before 31 Dec 2025, so a re-authorization that would continue it may not be observed yet |
| in_50_states_dc, fixed_location | as in authorizations |

## location_spells.csv.gz — one row per address spell

A location spell is one address continuously hosting at least one SNAP-authorized fixed-location retailer (any Record
ID), merging gaps of up to 365 days. Addresses are keyed by `location_key`: street number | standardized street name |
ZIP5, built exactly as in *Retailer Churn and Food Access* v0.1.0.

| column | definition |
|---|---|
| location_spell_id, location_id, spell_number | `<location_id>-<spell_number>`; address ID; order of the spell at the address |
| start_date / end_date | first authorization / last end of any SNAP store at the address within the spell |
| n_records, n_record_ids | authorization records and distinct stores (Record IDs) in the spell |
| any_large_store | a Large store (Supermarket, Super Store, Large Grocery) was authorized at the address during this spell |
| ever_large_store | the address hosted a Large store at some point in 2005–2025 |
| location_key | address key; `RID|<record_id>` when the record has no street address |
| street_number, street_name, city, state, zip5, county_fips, tract_geoid, geo_method | from the address's most recent authorization record |
| start_placeholder_1930, open_at_file_end, end_within_window_of_file_end, in_50_states_dc | as in store_spells |

## national_year.csv — national stock and flows, 2006–2025

| column | definition |
|---|---|
| coverage | `all` (states and territories) or `50 states + DC` |
| unit | `store` (store spells) or `location` (location spells) |
| store_group | `All fixed-location`, a single group, `Farmers' market`, `Delivery route` (store unit only) |
| year | calendar year |
| stock_jan1 | spells active on 1 January (start before 1 January, end on or after it, or open) |
| entries / exits | spells starting / ending during the year. Exits are empty for 2025 (the 365-day window is not yet observable). |
| entry_rate / exit_rate | entries / stock_jan1, exits / stock_jan1 |

## county_year.csv.gz — the same, by 2020 county

Columns: `county_fips, year, unit, store_group, stock_jan1, entries, exits, entry_rate, exit_rate`. Rows where a county
has no stock, entries or exits in a year are omitted (read them as zeros).

## tract_year.csv.gz — by 2020 census tract (wide)

| column | definition |
|---|---|
| tract_geoid, year | 2020 tract; calendar year 2006–2025 |
| stores_stock_jan1, stores_entries, stores_exits | fixed-location store spells |
| locations_stock_jan1, locations_entries, locations_exits | location spells |
| large_stores_stock_jan1, convenience_stock_jan1 | store spells of those groups active on 1 January |

Tract-years with no retailer activity are omitted. Exit columns are empty for 2025.

## qa_report.txt, stats.json

`qa_report.txt` is the quality report: row counts, agreement with the working paper, geocoding rates, consistency
checks and named spot checks. `stats.json` holds every number quoted in the documentation.
