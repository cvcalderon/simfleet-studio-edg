# F3.2g — DG_DISTANCE_PRIOR implementation note v1

## 1. TRAIN universes

Primary fitting universe:
- `TRAIN/distance_raw.csv`: 5,617 rows
- provenance: `RAW_WEGKM`
- target: `target_distance_prior_km`

Sensitivity-only universe:
- `TRAIN/distance_expanded_sensitivity.csv`: 6,145 rows
- 5,617 raw rows + 528 source-imputed rows
- never used to fit the five primary candidates

Optional upstream-context missingness remains explicit and does not trigger complete-case collapse:
- 80 rows missing source trip-count analogue;
- 32 rows missing valid time context;
- 217 rows with unresolved transition context.

## 2. DIST_BACKOFF_V1

1. origin + destination activity + departure period + primary activity + age
2. origin + destination activity + departure period + primary activity
3. origin + destination activity + departure period
4. origin + destination activity
5. destination activity
6. global raw-wegkm ECDF

Raw strict-TRAIN row count is the support count. Direct conditional sampling requires `source_n >= 30`. W_GEW determines probability mass inside an eligible cell.

## 3. Information boundary

Allowed semantic predictors are upstream generated state analogues plus static/scenario-known context. IDs, weights, provenance, quality flags, mode, route, `km_routing` and execution outcomes are excluded from X.

## 4. Outputs

The official TRAIN fit produces five unselected artifacts plus:
- feature/encoder/support manifests;
- report-only sensitivity-universe manifest;
- input/design/environment hash validation;
- backoff summary;
- TRAIN fit summary;
- fit validation and run manifest;
- complete internal checksums.
