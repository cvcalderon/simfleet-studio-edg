# F1-P_CONSTR G1 HOLD-THRESH-001 — threshold transfer rule v1

## Status

`PREOPEN — values frozen for commit; 1000A-1035 remains unacquired/unread/unauthorized.`

## Problem closed by this rule

The external senior-status holdout pre-registration defines two decision-driving TVD metrics but intentionally left their numeric thresholds as `CAL_LOCK_BEFORE_HOLDOUT_ACQUISITION`. The already-frozen `g1_thresholds_v1` contains four CAL-derived materiality tolerances, not senior-status-specific tolerances.

No hidden senior-specific threshold rule exists in the frozen amendment. Therefore a deterministic mapping must be frozen before any `1000A-1035` value I/O.

## Source evidence

Only the four already-frozen CAL materiality tolerances are used:

- `ACTIVITY_BY_AGE`: `0.07293353416541049`
- `LICENSE_BY_AGE_SEX`: `0.0815667541845037`
- `HH_CAR_STOCK_BY_SIZE`: `0.0660999637102583`
- `HH_BIKE_EBIKE_STOCK_BY_SIZE`: `0.07409481595332659`

No CAL rows are reopened. MiD TEST is not reopened. No `1000A-1035` values are acquired or read.

## Transfer rule

Define

`T = max(tau_j)`

over the four frozen CAL preservation-family materiality tolerances.

Therefore:

`T = 0.0815667541845037`

This maximum rule is chosen before holdout inspection because it is deterministic, conservative with respect to the previously frozen family-specific practical-resolution tolerances, and does not cherry-pick a favourable family.

## Interpretation

`T` is a **practical tolerance transferred from frozen CAL evidence**. It is **not** claimed to be a confidence interval, p-value, or sampling-error bound for the senior-status metric itself.

## Holdout decision rule

Both decision metrics must pass independently:

- `G1-HOLD-SEN-BERLIN-TVD <= 0.0815667541845037`
- `G1-HOLD-SEN-BEZ-WTVD <= 0.0815667541845037`

`G1-HOLD-SEN-BEZ-MAX` remains report-only.

There is no composite score and no averaging between the two decision metrics.

After first holdout value I/O:

- threshold tuning is forbidden;
- candidate selection is forbidden;
- same-lineage code tuning is forbidden;
- a scientific failure requires a new experimental lineage.
