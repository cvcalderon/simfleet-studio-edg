# F1-P_CONSTR-IMPL-03 — PREOPEN v1

**Parent:** `2f547ec53501245af1d605a866e19febfc5089b8`
**Status:** `PREOPEN_IMPLEMENTATION_ONLY`

## Scope

Implement TRAIN-only candidate construction at Bezirk level:

- `P_TRS_V1_FINAL`;
- `P_CONSTR_RMIN_V2_HD_U`;
- `P_CONSTR_RMIN_V2_HD_W`;
- common `H6_COMPLETION_V1` donor/materialization branch.

No PLR allocation is performed in IMPL-03.

## Frozen donor semantics

### P_TRS

- TRAIN strict 1..5 households only;
- whole-household sampling with replacement;
- probability proportional to `H_GEW`;
- no age/sex/household-size composition fitting;
- each Bezirk receives its exact non-6+ person total, but donor composition is not conditioned on the R_min target.

### P_CONSTR

Equivalence basis:

```text
household contribution vector
→ age_zensus_11_v1 × sex × exact household size
```

Fit pipeline:

```text
IPU_FRACTIONAL_CONTRIBUTION_V1
→ exact-household integerization
→ GREEDY_SINGLE_SWAP_L1 repair
```

`HD_U` and `HD_W` use the same fitted equivalence-class counts. They differ only in donor choice inside each class:

```text
HD_U = uniform
HD_W = H_GEW weighted
```

## 6+ common branch

The exact same source blueprint is used for all three candidates:

- TRAIN private 6+ household templates, `H_GEW` weighted;
- projected 6+ `age_zensus_11 × sex` target slots exactly assigned;
- TRAIN private-person donor exact match on target age×sex;
- `P_GEW` weighting where valid;
- mobility outcomes are not matching inputs.

## PRE-COMMIT anchors

Catalog:

```text
strict TRAIN HH       = 1219
TRAIN 6+ templates    = 8
TRAIN private persons = 2244
equivalence classes   = 249
age×sex support cells = 22/22
```

Scale S:

```text
P_TRS: persons=10000, HH=5309, fit L1=3968, max cell error=29
HD_U : persons=10000, HH=5485, fit L1=350,  max cell error=4
HD_W : persons=10000, HH=5485, fit L1=350,  max cell error=4
common 6+ branch = TRUE
TEST donor violations = 0
CAL donor violations  = 0
```

Scale M plan only:

```text
strict target persons      = 93127
strict target households   = 54026
positive equivalence class = 241
fit L1                     = 3172
max cell error              = 40
```

These are PREOPEN implementation regression anchors, not CAL selection results.

## Absolute boundaries

```text
CAL = UNREAD
MiD TEST read by IMPL-03 = FALSE
MiD TEST global = CONSUMED_BY_G2 / DO NOT REOPEN
1000A-1035 = UNREAD
PLR allocation = NOT PERFORMED
candidate selection = NOT PERFORMED
G1 threshold tuning = NOT PERFORMED
F3 = UNTOUCHED
G1 = OPEN
G2 = PASS / CLOSED / DO NOT REOPEN
```
