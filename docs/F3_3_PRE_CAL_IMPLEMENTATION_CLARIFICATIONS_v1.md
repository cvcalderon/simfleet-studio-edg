# F3.3a — PRE-CAL implementation clarifications v1

## Status

`FROZEN_BEFORE_CAL_INSPECTION`

F3.1c already freezes the scientific selection protocol. This document only resolves computational details that F3.1c leaves underspecified and that could otherwise change a CAL decision.

### C1 — 32-replicate point estimate

For metrics that require stochastic generated realizations, compute the metric independently for each of the 32 paired replicates and use the arithmetic mean of those 32 metric values as the point estimate.

This does not replace deterministic proper scores such as probability log-loss or discrete CRPS when those can be evaluated directly from predictive probabilities/PMFs.

### C2 — paired household bootstrap CI

Use 1000 paired household bootstrap replicates. For every bootstrap replicate, resample households with replacement; all observations in a sampled household retain their original P_GEW/W_GEW and receive the household multiplicity. Compute `improvement = incumbent_metric - challenger_metric` because all frozen primary metrics are lower-is-better.

The 95% CI is the percentile interval `[q0.025, q0.975]` of paired improvements. Promotion requires its lower endpoint to be strictly `> 0`.

### C3 — grid selection inside A or B

For a candidate family with multiple preregistered grids:

1. discard grids with a HARD failure;
2. discard grids that fail the frozen guardrails against the current lower-complexity incumbent;
3. among remaining grids, choose the lowest point primary metric;
4. if point metrics are exactly equal, choose lexical `grid_id`.

The practical promotion margin and bootstrap-CI test are then applied between that family grid and the current incumbent.

### C4 — sequential family promotion

Start from REF. Evaluate the best eligible A grid against the incumbent. If A is not promoted, REF remains incumbent. Then evaluate the best eligible B grid against the current incumbent. This directly operationalizes:

`REFERENCE_BASELINE < CORE_CANDIDATE_A < CORE_CHALLENGER_B`.

### C5 — bootstrap seed namespace

Bootstrap RNG is separate from candidate runtime draws:

`SHA256(F3_3_BOOTSTRAP_V1 | master_seed | component | incumbent_artifact_id | challenger_artifact_id) -> uint64`

Candidate generation still uses the frozen F3.1c runtime stream.

### C6 — PART_B cross-fit folds

Assign each CAL household deterministically:

`SHA256(F3_3_PART_B_CAL_FOLD_V1 | master_seed | source_household_id) mod 5`

All people from the same household share the same fold.

## Non-changes

These clarifications do **not** change candidate families, features, TRAIN fits, promotion margins, guardrail tolerances, CAL/Test roles or the component DAG.
