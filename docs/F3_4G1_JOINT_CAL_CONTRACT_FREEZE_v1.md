# F3.4g-1 — Joint selected-vs-all-reference CAL Contract Freeze v1

**Required parent:** `5913f9604378cf2356a9251accf59105c51e9163`

## Entry state

All five D_GEN components are MAIN_FROZEN:

```text
PA1
→ COUNT_REF
→ CHA2
→ TIME_B_TB2
→ DIST_REF
```

The all-reference comparator is:

```text
PART_REF
→ COUNT_REF
→ CHAIN_REF
→ TIME_REF
→ DIST_REF
```

Joint CAL has not been executed. TEST remains sealed. Formal G2 remains
`NOT_EVALUATED`.

## Purpose

Freeze the exact semantics of the final CAL gate required before any held-out
TEST opening.

F3.4g-1 reads **zero CAL rows**. It only freezes:

- selected and all-reference artifact identities;
- CAL input universe and expected physical row counts;
- end-to-end propagation semantics;
- CRN/seed protocol;
- static component-primary dominance witnesses;
- decision-driving Joint metrics and frozen tolerances;
- hard invariants;
- PASS/FAIL semantics;
- TEST/G2 boundary.

## CAL inputs

The future Joint runner may open exactly the eight frozen CAL files:

| File | Rows |
|---|---:|
| person_day_context.csv | 469 |
| participation.csv | 460 |
| trip_count.csv | 381 |
| chain_days.csv | 319 |
| chain_transitions.csv | 1,065 |
| time_trips.csv | 1,243 |
| distance_raw.csv | 1,147 |
| distance_expanded_sensitivity.csv | 1,257 |

If each physical file is opened once, the audit count is **6,341 rows**.

No TEST path may be opened.

## Joint generation

Both pipelines are generated from the same 469-row static person-day context,
using:

- scenario `CAL_EVAL_V1`;
- master seed `20260926`;
- 32 paired stochastic replicates;
- common random numbers;
- identical seed schedule across the two pipelines.

There is no runtime teacher forcing.

Metric-specific denominator and missingness semantics are inherited unchanged
from the accepted component CAL contracts.

## Component dominance

Proper-score primaries that the component contracts explicitly do not redefine
under propagation are not given a new Joint target.

`selected_component_dominated` is established from the accepted component
freezes. The witness table records the exact selected-vs-reference primary
values.

## Pipeline degradation

The future Joint runner compares generated outcomes for the selected and
all-reference pipelines.

For each decision-driving metric:

```text
worsening = selected error - all-reference error
PASS iff worsening <= frozen tolerance
```

The exact matrix is `docs/F3_4G1_JOINT_METRIC_MATRIX_v1.csv`.

No composite score is permitted.

## Hard gate

The existing `cal_joint_gate` primitive remains authoritative. A later real
Joint PASS requires:

- zero structural violations;
- zero temporal violations;
- zero NoFutureInformation violations;
- no selected component dominated;
- no material selected-pipeline degradation;
- all five selected artifact identities frozen;
- no post-CAL design change.

## Boundary

F3.4g-1 itself leaves:

```text
Joint CAL rows read = 0
Joint gate evaluated = false
Joint real CAL = NOT_AUTHORIZED
TEST = SEALED
TEST rows read = 0
formal G2 = NOT_EVALUATED
```

A successful commit authorizes only implementation of the synthetic PRE-OPEN
runner for the Joint comparison.
