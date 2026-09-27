# F3.2g — DG_DISTANCE_PRIOR objective freeze v1

F3.2g implements the already-frozen distance-prior candidate slate on **TRAIN only**.

## Primary evidence

Primary target: raw MiD `wegkm`, materialized as `target_distance_prior_km` under the `DIRECT_SOURCE_DISTANCE_VALID` universe.

- TRAIN raw-distance rows: **5,617**
- fitting weight: `W_GEW`
- generated value: M2 path-length prior for M3
- it is not exact OD separation and not routed/executed distance

`wegkm_imp` remains report-only sensitivity evidence. `km_routing` is forbidden.

## Candidate slate

- `DIST_REF / REFERENCE`: weighted unconditional raw-wegkm ECDF.
- `DIST_A / DA1`: weighted conditional inverse-ECDF with `DIST_BACKOFF_V1`, direct support iff raw `source_n >= 30`.
- `DIST_B / DB1`: q=.05,.10,.25,.50,.75,.90,.95; depth=2; leaves=4; min_leaf=30; L2=1.
- `DIST_B / DB2`: same quantiles; depth=3; leaves=8; min_leaf=30; L2=1.
- `DIST_B / DB3`: same quantiles; depth=3; leaves=8; min_leaf=60; L2=1.

Expected artifacts: **5**.

Every artifact remains `FITTED_TRAIN_ONLY_NOT_SELECTED`. No TRAIN metric selects a candidate. CAL remains unopened and TEST remains sealed.
