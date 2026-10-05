# F1-P_CONSTR-CAL-01 — CAL evaluation contract v1

## 1. Boundary

This PREOPEN freezes evaluation primitives only. It does **not** authorize or read CAL rows.

At entry and exit:

```text
CAL rows read        = 0
candidate selection  = NONE
g1_thresholds_v1     = NOT_FROZEN
MiD TEST             = DO NOT READ / G2 CLOSED
1000A-1035           = UNREAD
PLR allocation       = NOT PERFORMED
F3                   = UNTOUCHED
G1                   = OPEN
```

## 2. Candidate universe

Exactly three frozen candidates are eligible:

```text
P_TRS_V1_FINAL
P_CONSTR_RMIN_V2_HD_U
P_CONSTR_RMIN_V2_HD_W
```

No new population candidate, seed family, donor rule, equivalence class, 6+ completion rule or fit algorithm may be introduced in CAL-01.

## 3. Empirical vs synthetic weighting

The empirical CAL reference uses the original MiD survey weights:

- persons: `P_GEW`;
- households: `H_GEW`.

Synthetic populations already represent explicit population counts. Therefore synthetic person/household rows use **unit weight**. `source_person_weight` and `source_household_weight` are provenance and must not be multiplied into synthetic evaluation weights.

## 4. Decision-driving preservation families

### ACTIVITY_BY_AGE

`P(primary_activity_status | age_infr_class)` using observation-compatible activity rows.

### LICENSE_BY_AGE_SEX

`P(car_driver_license | age_infr_class, sex)` using observed YES/NO licence rows only.

### HH_CAR_STOCK_BY_SIZE

Household car-stock category conditional on household-size class.

### HH_BIKE_EBIKE_STOCK_BY_SIZE

Bike and e-bike stock are evaluated as two explicit submetrics conditional on household-size class. The family error is the maximum of the two submetric errors so improvement in one cannot mask degradation in the other.

## 5. Conditional distance and support

Every component uses total variation distance (TVD) between empirical-CAL and synthetic conditional categorical distributions.

A conditioning cell with unweighted eligible CAL support `<30` is `LOW_N` and report-only. Decision-driving family error is the CAL-eligible-weight-share weighted mean TVD over support-OK cells. If a family has no support-OK cells, evaluation is a HARD failure rather than silently relaxing the rule.

## 6. Materiality threshold derivation

Numerical thresholds are intentionally **not known in PREOPEN**.

For each family `j` after controlled CAL authorization:

1. compute baseline error `E0_j = D(P_TRS, CAL)`;
2. bootstrap CAL households atomically with replacement 1000 times;
3. retain every sampled household's persons and original survey weights;
4. recompute `E0_j^b`;
5. freeze:

```text
tau_j = Q95( | E0_j^b - E0_j | )
```

using NumPy quantile method `higher`, master seed `20261005`, substream `F1_PCONSTR_CAL_MATERIALITY_V1`.

The resulting numeric `tau_j` values become `g1_thresholds_v1` only after MAIN audits the CAL RunBundle. TEST/holdout results can never alter them.

## 7. Selection without composite score

### Stage 1 — HD_U vs HD_W

`HD_U` is the simpler incumbent. `HD_W` is promoted only if:

- it improves at least one preservation family by more than that family's `tau_j`; and
- it degrades no preservation family by more than `tau_j`.

Otherwise retain `HD_U`. Exact or inconclusive ties retain `HD_U`.

### Stage 2 — constrained winner vs P_TRS

The constrained winner is retained only if all are true:

1. `target_fit_l1` is strictly lower than P_TRS;
2. `target_fit_max_abs` is no worse than P_TRS;
3. no preservation family degrades relative to P_TRS by more than `tau_j`;
4. no HARD engineering/integrity/reproducibility failure occurs.

Otherwise retain P_TRS.

No scalar composite score is permitted.

## 8. Engineering cost

Current-lineage operational feasibility is already evidenced by accepted IMPL-03 A1. CAL-01 does not invent an arbitrary wall-time ratio to discriminate candidates. A runtime, memory, integrity or reproducibility failure in the controlled CAL run is HARD and prevents promotion.

## 9. After controlled CAL

The CAL runner may only produce a **proposal**:

```text
PROPOSED_BY_FROZEN_CAL_RULES_AWAITING_MAIN_FREEZE
```

MAIN must independently audit and freeze:

- selected candidate;
- `g1_thresholds_v1`;
- CAL metrics;
- exact Git commit;
- seed schedule.

Only after that may a separate task authorize reading `1000A-1035` for the preregistered G1 feature holdout.
