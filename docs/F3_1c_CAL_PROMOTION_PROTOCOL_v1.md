# F3.1c — CAL promotion protocol v1

**Parent F3.1b commit:** `ce99ff2f175fcc2df34cca3607754b4de9c4605d`  
**TEST:** SEALED  
**Formal G2:** NOT EVALUATED

## 1. Principle

CAL selects only among the families, feature subsets and hyperparameter grids frozen **before CAL inspection**. There is no overall composite score. Selection is component-wise in the frozen D_GEN DAG order.

## 2. Evaluation modes

For downstream component selection, two CAL views are required:

1. **ISOLATED / teacher-forced evaluation** — source CAL upstream state may be supplied only to isolate the component under evaluation. This is an evaluation device and is forbidden at runtime.
2. **PROPAGATED evaluation** — after a component is selected, rerun CAL with already-selected upstream components generating their own state.

A candidate cannot be promoted if isolated gains disappear through a hard failure in propagated evaluation.

## 3. Stochastic replication

Each stochastic candidate generates **32 paired replicates per CAL person**. Candidate comparisons use common random numbers derived from master seed `20260926`. This reduces variance without making candidate RNG mechanics different.

## 4. Bootstrap

Uncertainty is estimated with **1000 paired household bootstrap replicates**, resampling the household as the atomic unit. Original `P_GEW`/`W_GEW` remain attached to observations inside each resampled household. Confidence level: **95%**.

## 5. Promotion rule

Complexity order is:

`REFERENCE_BASELINE < CANDIDATE_A < CHALLENGER_B`.

Promotion from a simpler candidate to a more complex one requires simultaneously:

- every HARD invariant PASS;
- point improvement on the component primary metric at least the predeclared practical margin;
- 95% paired household-bootstrap CI for improvement strictly above zero;
- no aggregate or supported-subgroup guardrail degradation above its frozen tolerance.

If these conditions are not met, retain the simpler candidate. `LOW_N` groups (`source_n < 30`) remain report-only and cannot force pooling or promotion.

## 6. PART_B probability calibration

Only `NONE` and `WEIGHTED_SIGMOID` are preregistered. Sigmoid calibration is evaluated with five household-level cross-fit folds inside CAL. It is retained only if weighted Bernoulli log-loss improves by at least `0.002` and trip-day-share error does not worsen by more than `0.005`. After the family/grid is selected, the authorized sigmoid calibrator may be fit on all CAL and frozen as part of the artifact.

## 7. Joint pipeline gate before TEST

After all five components are selected, compare the selected D_GEN pipeline against the all-reference pipeline on CAL. Opening TEST requires:

- zero structural, temporal and NoFutureInformation violations;
- no selected component dominated by a simpler candidate under the rules above;
- no primary/guardrail metric materially worse than the all-reference pipeline beyond the corresponding frozen worsening tolerance;
- frozen artifact manifests/hashes for all selected components;
- no new candidate, feature, threshold or hyperparameter introduced after CAL inspection.

Passing this gate **does not equal formal G2 closure**. It only authorizes the later held-out TEST evaluation under the already-frozen protocol.
