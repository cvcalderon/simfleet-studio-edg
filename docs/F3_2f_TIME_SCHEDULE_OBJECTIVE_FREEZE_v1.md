# F3.2f — DG_TIME_SCHEDULE objective freeze v1

This implementation consumes **TRAIN only** and implements the already-frozen F3.1b/F3.1c slate.

## Candidate slate

- `TIME_REF`: weighted empirical departure-hour reference (`W_GEW`).
- `TIME_A`: weighted conditional empirical temporal kernel with `TIME_BACKOFF_V1`.
  - `TA1`: bandwidth `0 min`
  - `TA2`: bandwidth `15 min`
  - `TA3`: bandwidth `30 min`
- `TIME_B`: LightGBM quantile temporal challenger.
  - quantiles: `.05,.10,.25,.50,.75,.90,.95`
  - `TB1`: depth 2, leaves 4, min leaf 30, L2 1
  - `TB2`: depth 3, leaves 8, min leaf 30, L2 1
  - `TB3`: depth 3, leaves 8, min leaf 60, L2 1

Expected artifacts: **7**.

## TRAIN universe

`TRAIN/time_trips.csv`, exactly `6103` `DIRECT_TEMPORAL_VALID` rows. Optional chain/K/prefix context is retained explicitly; it never causes complete-case collapse.

## Semantics

Departure/arrival/duration are **planned schedule quantities**, not executed route travel-time truth. Mode, route, service conditions and execution remain downstream.

No TRAIN metric selects a candidate. CAL remains unopened and TEST remains sealed.
