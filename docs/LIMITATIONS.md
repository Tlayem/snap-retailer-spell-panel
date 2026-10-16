# Limitations

1. **An authorization is not a store being open.** The source records SNAP authorization, not whether a business is
   trading. A store can keep trading after leaving SNAP, and a closed store's authorization can linger until FNS
   removes it. Every exit here is an exit from SNAP retail.

2. **Some end dates are administrative.**
   - 54 end dates are each shared by 1,000 or more records nationally, and
     119,153 records end on one of them (`end_on_batch_date`).
   - These look like batch actions, such as reauthorization non-response. They date when FNS recorded the exit, not
     when trading stopped, so annual exit counts are lumpy.

3. **The continuity window is a judgment.**
   - Gaps of 365 days or less are treated as continuous, for stores and for addresses.
   - Spells ending within 365 days of 31 Dec 2025 may still be continued by a re-authorization not yet
     observed (`end_within_window_of_file_end`), so annual exits stop at 2024.
   - `04_spells.py` rebuilds the spells at any window.

4. **Coverage starts in 2005.**
   - The file lists retailers authorized at any time in 2005–2025. Stores that left before 2005 are absent, and earlier
     spells of a store active in 2005 are not seen.
   - 6,666 records carry a 1 January 1930 placeholder authorization date; their true start
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
     500 m.
   - 5,413 records (0.78%) fall in a different
     county from the one FNS names. These are mostly stores near county lines, Virginia independent cities, and errors
     in the FNS county field. Both values are kept.

7. **2020 geography for every year.** All records are placed in 2020 tracts and counties, whatever their year. This
   gives one consistent geography, but users linking to data on 2010 tracts need a crosswalk.

8. **Store type is one value per Record ID** and can lag a change in format. Grouping the 17 FNS store types into
   five fixed-location groups is a judgment.

9. **Farmers' markets and delivery routes** keep their store spells but have no location spells, because their
   address is a market site or a route base.
