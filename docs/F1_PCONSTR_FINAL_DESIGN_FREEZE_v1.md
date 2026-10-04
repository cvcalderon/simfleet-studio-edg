# F1-P_CONSTR-PHH-V1 — FINAL FREEZE DESIGN v1

**Date:** 2026-10-04  
**Status:** `FINAL_DESIGN_FROZEN_READY_FOR_IMPLEMENTATION`  
**G1:** `OPEN`  
**G2:** `PASS / CLOSED / DO NOT REOPEN`

## 1. Decision

The source-acquisition blocker is resolved. `P_CONSTR` can now be frozen as a coherent model with a strict separation between:

```text
1000A person-domain evidence -> demographic hard fit / fit objective
5000H + HH_SIZE_NAT          -> household structural/spatial prior
```

The definitive fitting basis is:

```text
R_MIN_PHH_FIT_V2 =
BEZIRK × age_zensus_11_v1 × sex × HSHGR2
```

`age_infr_class` remains canonical and is not replaced.

## 2. Person-domain reconciliation

The authoritative fit source is `1000A-3082`, anchored by the published Bezirk total-person counts in `1000A-1029`.

For each Bezirk define integer cells:

```text
x[b,a,s,h] >= 0
```

Hard constraints:

1. total persons exactly equal the published 1000A-1029 Bezirk total;
2. published-zero 3082 detailed cells remain zero;
3. for household sizes 1..5, each person margin is divisible by its exact household size;
4. all cells are integer and nonnegative.

The remaining Cell-Key inconsistency is resolved transparently by a hierarchical objective, never by overwriting source values. Stages 1–3 are lexicographically locked at their exact integer optima; stage 4 uses `CANONICAL_WEIGHTED_LINEAR_V1` only as a deterministic tie-break among stage-1/2/3 optima.

### Reference feasibility audit

> **IMPL-01 operational amendment R1.** The original design-only reference used an exact per-cell lexicographic stage-4 tie-break. PRE-COMMIT execution on the authoritative Linux/Python environment showed that this required hundreds of MILP solves and was not operationally portable. Before any commit, CAL, TEST, or holdout read, stage 4 was replaced by `CANONICAL_WEIGHTED_LINEAR_V1`, a single deterministic weighted MILP after stages 1–3 are locked. Scientific priorities and stage-1/2/3 optima are unchanged. The implementation anchor for changed detailed cells becomes 56; the decision-driving anchors remain 161/272/478 and max adjustment 12.

A design-only MILP audit over all 12 Bezirke proves the contract feasible:

```text
12/12 Bezirke feasible
1,584 detailed cells
56 cells adjusted
stage-1 detailed L1 adjustment = 161 persons
maximum detailed adjustment    = 12 persons
P99 detailed adjustment        = 3 persons
stage-2 HSHGR2-margin L1       = 272
stage-3 sex×HSHGR2-margin L1   = 478
```

These are implementation regression anchors, not new observations.

## 3. Scale projection

The definitive private-household person-domain Berlin total is:

```text
3,532,081 persons
```

The full-scale reconciled cube is frozen first. S/M/L are then deterministic integer projections with exact target N, preserved structural zeros and household-size divisibility.

## 4. Household sizes 1..5

For each exact size h in 1..5:

```text
H_h = P_h / h
```

is exact after constrained integerization.

Whole-household TRAIN donors are represented through equivalence classes defined by their contribution to the joint fit basis. The historical U/W materialization ablation is retained:

```text
P_CONSTR_RMIN_V2_HD_U -> uniform donor within equivalence class
P_CONSTR_RMIN_V2_HD_W -> H_GEW-weighted donor within equivalence class
```

CALIBRATION selects between them.

## 5. 6+ household branch

The source evidence is intentionally separated:

```text
1000A -> exact person-domain P6+ target
5000H -> household-domain H6+ structural prior
```

The observed conversion among exact multiperson sizes 2..5 is:

```text
rho_multi_2_5 = 0.993516178214743
```

Applying this to `5000H` and deterministic largest-remainder integerization gives:

```text
Berlin H6+ model-fixed structural target = 28,343 households
Berlin P6+ source person target           = 242,700 persons
implied mean size                         ≈ 8.5630
```

`28,343` is **not** a source-hard count. It is a frozen EDG structural target derived from the household-domain prior.

### Individual latent sizes

No arbitrary 6/7/8/... distribution is invented. For each Bezirk:

```text
E = P6 - 6*H6
```

and the E extra members are assigned by a seeded uniform weak composition across H6 labeled households.

Therefore:

```text
n_i >= 6
count(households) = H6
sum(n_i) = P6
```

exactly.

This is a minimum-assumption EDG-derived completion. Individual sizes are never labelled source-observed.

### 6+ member attributes

The 6+ roster is explicitly synthetic because MiD is top-coded/censored for this branch.

- household-level template: TRAIN private 6+ donor household, H_GEW weighted;
- each member receives an exact target `age_zensus_11_v1 × sex` slot from the reconciled 6+ cube;
- static person attributes are copied from TRAIN private-person donors exact-matched on that age×sex cell, with replacement;
- mobility outcomes are forbidden matching inputs;
- TEST donors are forbidden.

The same 6+ branch is used in P_TRS and P_CONSTR so the ablation does not confound the comparison.

## 6. Spatial policy

Formal demographic fit ends at Bezirk.

`HH_SIZE_NAT@BZR/PLR` remains valuable but only as household-domain spatial evidence.

Observed PLR use household-size-specific weights where available. The two PLR without statistical observations remain explicit `NO_STAT_TARGET` units and are not zero-imputed.

Their frozen fallback is `PLR_NO_STAT_AREA_PRIOR_V1`: area × median household density of observed sibling PLRs in the parent BZR, with parent BZR household-size composition. This is modelled spatial allocation and is excluded from the G1 hard fit score.

## 7. G1 evidence

### G-HARD

All structural violations must equal zero, including orphan persons, multi-household membership, atomicity errors, size mismatches, invalid zones, split leakage, forbidden TEST donor use, NoFutureInformation violations, source published-zero violations, and 6+ count/sum violations.

### Source reconciliation regression

A conforming implementation must reproduce the reference objective values:

```text
stage1 = 161
stage2 = 272
stage3 = 478
max detailed adjustment = 12
```

with `CANONICAL_WEIGHTED_LINEAR_V1` stage-4 tie-breaking.

### Empirical fit and preservation

Fit metrics remain MAE/relative error/MAPE where defined, percentiles and small-cell analyses by geography/control.

The original preservation families remain frozen:

```text
P(primary_activity_status | age_infr_class)
P(car_driver_license | age_infr_class, sex)
P(household car stock | household_size_class)
P(household bike/e-bike stock | household_size_class)
```

Numerical materiality thresholds and the HD_U/HD_W winner are selected with TRAIN+CALIBRATION only and frozen before G1 TEST.

## 8. TEST boundary

The F3 held-out TEST runner is never rerun and G2 is never reopened.

G1 may only perform its separately preregistered population-preservation evaluation after candidate and thresholds are frozen. Because mobility TEST outcomes were previously consumed by G2, this is explicitly recorded as a limitation; no G1 decision may tune M2/F3 or reuse those outcomes.

## 9. Status

```text
F1-SOURCE-PHH-001A = SUPERADO
F1-SOURCE-PHH-001B = SUPERADO_WITH_LIMITATION
F1-SOURCE-HH-002A  = SUPERADO
F1-SOURCE-HH-002B  = SUPERADO

F1-P_CONSTR-PHH-V1 FINAL DESIGN = FROZEN
IMPLEMENTATION                      = NOT STARTED
G1                                  = OPEN
G2                                  = PASS / CLOSED
```

The next task is implementation against the frozen repository baseline. At that point the GitHub project is required.
