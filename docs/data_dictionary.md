# Data dictionary

## Source form fields (ODK export / OData, after `normalise_columns`)
| Field | Type | Notes |
|---|---|---|
| instance_id (KEY) | text | Unique per submission; primary key everywhere |
| submitted_at (SubmissionDate) | datetime (UTC) | Used as the incremental-load watermark |
| farmer_id | text | Reconciled to `data/reference/farmers_master.csv` |
| region | text | Title-cased; compared with the master list |
| season | text | `YYYY` + `A` (long rains, plant Feb-May) or `B` (short rains, plant Aug-Nov) |
| crop | text | maize, beans, sorghum, potato, wheat (synonyms mapped, e.g. corn -> maize) |
| area_ha | number | Declared plot area, 0.05-50 ha |
| planting_date, harvest_date | date | Harvest must be after planting |
| yield_kg, fertilizer_kg | number | Totals for the plot (not per ha) |
| input_cost, price_per_kg | number | KES |
| plot_boundary | geoshape | ODK text `lat lon alt acc; ...` or GeoJSON Polygon |
| plot_gps | geopoint | ODK text or GeoJSON Point |

## Derived (table `clean_records`)
| Field | Definition |
|---|---|
| yield_kg_ha | yield_kg / area_ha |
| fertilizer_kg_ha | fertilizer_kg / area_ha |
| revenue | yield_kg x price_per_kg |
| gross_margin | revenue - input_cost (excludes unpaid family labour) |
| days_to_harvest | harvest_date - planting_date |
| polygon_area_ha | Area of plot_boundary (equirectangular approximation, fine for plots under ~50 ha) |
| has_warning | 1 if any warning-level rule fired |

## Aggregates
Yield = sum(yield_kg) / sum(area_ha) (area-weighted, not a mean of ratios).
Performance index = a crop's yield in the group / that crop's all-data yield x 100, averaged across crops weighted by area. Used because kg/ha is not comparable between crops.

## Tables
`raw_submissions` (untouched payload) -> `clean_records` (passed all gates) ; `dqc_issues` (every rule hit, with detail); `etl_runs` (run log + watermark).
Rules: see `pipeline/dqc.py:RULES` (single source of truth, also shown on the dashboard).
