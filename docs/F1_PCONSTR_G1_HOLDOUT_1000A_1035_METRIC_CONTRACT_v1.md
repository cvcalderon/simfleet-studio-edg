# F1-P_CONSTR G1 1000A-1035 metric contract v1

Status: **PREOPEN FROZEN SEMANTICS / NO HOLDOUT VALUE I/O**

## Holdout identity

`1000A-1035` — *Personen: Seniorenstatus eines privaten Haushalts (ausführlich)*.
The statistical domain is persons living in private households. A senior is a person aged 65 or older.

## Five mutually exclusive leaves

Every synthetic private household receives exactly one category from its complete age roster:

1. `SINGLE_SENIOR_HOUSEHOLD`: household size 1 and the person is age >= 65.
2. `TWO_PERSON_ALL_SENIOR_HOUSEHOLD`: household size 2 and both persons are age >= 65.
3. `MULTIPERSON_ALL_SENIOR_HOUSEHOLD`: household size >= 3 and every member is age >= 65.
4. `SENIOR_AND_YOUNGER_HOUSEHOLD`: at least one member age >= 65 and at least one member age < 65.
5. `NO_SENIOR_HOUSEHOLD`: no member is age >= 65.

The scored unit is **person**, not household. Every person inherits the category of their household.

The source total row and the overlapping aggregate `ALL_SENIOR_HOUSEHOLDS_AGGREGATE` are never TVD leaves.

## Decision metrics

### G1-HOLD-SEN-BERLIN-TVD

For each leaf `c`, aggregate person counts over the 12 Berlin Bezirke and normalize separately for synthetic and official distributions.

`TVD_BERLIN = 0.5 * sum_c |p_syn(c) - p_off(c)|`

The Berlin reference is the sum of the 12 Bezirk leaf counts; no separately perturbed state-level total is mixed into this metric.

### G1-HOLD-SEN-BEZ-WTVD

For every Bezirk `b`, compute the same five-leaf TVD. Let `N_off,b` be the sum of the five official leaf person counts for that Bezirk.

`WTVD = sum_b N_off,b * TVD_b / sum_b N_off,b`

The weights therefore come from the official holdout leaf totals, not from synthetic totals.

### G1-HOLD-SEN-BEZ-MAX

`MAX_BZ = max_b TVD_b`

This is report-only and cannot independently pass/fail G1.

## Missing/disclosure policy

`-` is a published zero. `.` and `/` are not zero and must remain unavailable/uncertain.

Both decision metrics require all five numeric leaves for all 12 Berlin Bezirke. If any required leaf is unavailable, no imputation, redistribution, residual fill or renormalization over the remaining leaves is allowed. The decision result becomes `INDETERMINATE_HOLDOUT_SUPPORT`.

## Realization and randomness

The primary validation realization is scale `M`, consistent with the frozen population protocol (`M = primary validation/benchmark`). The selected algorithm is `P_CONSTR_RMIN_V2_HD_U`.

Frozen generation seeds inherited from IMPL-03:

- candidate master seed: `20261005`
- H6 master seed: `20261004`

The holdout metric itself uses **no randomness**.

The M-scale selected-candidate realization is not yet frozen. This is blocker `HOLD-MREAL-001`.

## Numeric decision thresholds

The existing `g1_thresholds_v1` is frozen, but it contains tolerances for four CAL preservation families and does not define an explicit mapping to the two senior-status decision metrics.

Therefore no numeric senior-status pass/fail threshold is defined in this PREOPEN. Implicit reuse, minimum, maximum, mean or any other post-hoc combination of those four values is forbidden.

This is blocker `HOLD-THRESH-001` and must be resolved before `1000A-1035` source values are acquired/read.
