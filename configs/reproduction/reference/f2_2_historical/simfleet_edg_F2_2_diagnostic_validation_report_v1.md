# SimFleet-EDG V2 — F2.2
## Diagnostic validation of `D_REPLAY_EXACT_V1` and `D_MATCH_FULLDAY_V1`

**Fecha:** 2026-09-22  
**Fase:** F2 — Replay / Matching diagnostics  
**Estado:** SUPERADO  
**Gate:** G1 remains open; G2 is **not** evaluated in this phase.  
**Population:** `P_TRS_EXP_V1_M`  
**Evidence label:** `PRE-G1 EXPERIMENTAL DIAGNOSTIC`

---

## 1. Objective

Freeze and execute the demand-validation metrics that will later be reused for G2, while keeping three effects separate:

```text
1. exact replay fidelity
2. matching-induced distortion
3. complete-diary selection bias
```

A diagnostic difference is reported; it is **not** converted into a pass/fail threshold in F2.

---

## 2. Reference populations

Primary references are strict-TRAIN empirical evidence and retain their F0 eligibility rules:

```text
participation      -> REF_TRAIN_BINARY
trip count         -> REF_TRAIN_CORE_STRICT_COUNT
purpose            -> REF_TRAIN_DIRECT_PURPOSE
departure time     -> REF_TRAIN_DIRECT_TIME_VALID
transitions        -> REF_TRAIN_TRANSITION
distance primary   -> REF_TRAIN_DISTANCE_RAW
return-home        -> REF_TRAIN_FULL_FUNCTIONAL
```

Person-day references use `P_GEW`; trip references use `W_GEW`.

`REF_FULLDAY_POOL` is not a target. It is the diagnostic selection pool used to quantify what changes when complete diaries are required.

---

## 3. Participation

Strict-TRAIN empirical reference:

```text
P(TRIP_DAY) = 87.9248%
```

Complete-diary donor pool:

```text
P(TRIP_DAY) = 83.8808%
Δ vs strict reference = -4.04 pp
```

Exact replay, wherever strict binary participation is observable:

```text
coverage = 87,591/100,000
P(TRIP_DAY) = 88.5000%
Δ = +0.58 pp
```

Full-day matching:

```text
P(TRIP_DAY) = 84.4260%
Δ = -3.50 pp
```

Interpretation: any large D_MATCH difference must first be decomposed into **full-day selection** and **matching**; it cannot be attributed directly to the matching algorithm alone.

---

## 4. Trips per person-day

Strict-count empirical reference:

```text
E[trips/day] = 3.1902
```

Complete-diary pool:

```text
E[trips/day] = 2.8691
Δ = -0.3211
```

Replay count-eligible subset:

```text
coverage = 82,873/100,000
E[trips/day] = 3.2618
Δ = +0.0716
```

Matched population:

```text
E[trips/day] = 2.9151
Δ = -0.2751
```

The complete trip-count distributions are retained in the distribution-detail artifact and compared with TVD.

---

## 5. Purpose, timing and sequence

TVD against the broad strict-TRAIN empirical reference:

| Metric | D_REPLAY | D_MATCH |
|---|---:|---:|
| Purpose | 0.0364 | 0.0351 |
| Departure hour | 0.0354 | 0.0275 |
| Activity transition | 0.0667 | 0.0634 |

These values include the effect of restricting outputs to fully reconstructable mobile diaries. The corresponding `REF_FULLDAY_POOL` TVDs are therefore reported separately as the selection-bias component.

---

## 6. Return-home

Among mobile days with sufficient functional evidence:

```text
strict empirical reference = 85.9935%
complete-diary pool        = 86.5118%

D_REPLAY                   = 85.3731%
D_MATCH                    = 85.9877%
```

The metric is defined as:

```text
last resolved destination activity == HOME
```

and is not applied to zero-trip days.

---

## 7. Distance

Primary distance validation uses **raw substantive `wegkm` only**.

Wasserstein distance to the weighted strict-TRAIN raw-distance reference:

```text
D_REPLAY = 2.7334 km
D_MATCH  = 2.0136 km
```

A second sensitivity metric uses:

```text
raw wegkm
else source wegkm_imp
```

with provenance preserved.

`km_routing` remains excluded.

---

## 8. Conditional preservation

The first reusable conditional diagnostics are:

```text
P(TRIP_DAY | age)
P(TRIP_DAY | sex)
P(TRIP_DAY | primary activity)
P(TRIP_DAY | household size)

E[trips/day | same groups]
```

Cells with fewer than 30 strict-TRAIN source rows are flagged `LOW_N`; they are not silently pooled.

Among `OK` cells, the maximum absolute participation deviation observed is:

```text
D_REPLAY = 7.10 pp
D_MATCH  = 15.93 pp
```

This is descriptive, not an F2 acceptance threshold.

---

## 9. Complete-diary selection bias

Requiring a fully functional and temporally valid diary changes the empirical support before any matching occurs.

Static-distribution TVDs:

- `age_infr_class`: 0.0419
- `sex`: 0.0051
- `primary_activity_status`: 0.0440
- `household_size_class`: 0.0127


Outcome-level selection effects are stored for participation, trip count, purpose, timing and transitions.

Therefore:

```text
D_MATCH difference
=
complete-diary selection
+
matching / weighting
+
finite donor reuse
```

not simply “matching error”.

---

## 10. Diary diversity

`D_MATCH` maps 100,000 synthetic persons onto a finite empirical diary pool.

```text
full-day donors available = 1,658
unique donors used        = 1,637
effective donor count     = 1101.5
top-10 donor share        = 2.72%
```

Repeated assignment is expected for a diagnostic matcher, but it must remain visible because synthetic N does not create new observed diary diversity.

---

## 11. Metric implementation frozen for later G2

F2.2 freezes the **definitions**, not the final numeric thresholds.

Reusable G2 metric families:

```text
Participation
TripCount
MobileChainLength
Purpose
DepartureTime
ReturnHome
ActivityTransitions
Distance
Conditional participation
Conditional trip count
```

For final `D_GEN`, the model will be compared against held-out evidence under the same definitions, rather than inventing a new metric suite after observing results.

---

## 12. Validation

```text
PASS  = 18
FAIL  = 0
TOTAL = 18
```

Checks verify:

- strict TRAIN reference scope;
- exact F0 eligibility per metric;
- `P_GEW` / `W_GEW` weighting;
- complete D_MATCH coverage;
- no mode metric;
- no `km_routing`;
- static-only conditional groups;
- explicit LOW_N handling;
- diagnostic selection-bias treatment.

No metric-result threshold is tuned in F2.2.

---

## 13. Status

```text
F2.2 = SUPERADO

D_REPLAY_EXACT_V1  = VALIDATED_DIAGNOSTIC
D_MATCH_FULLDAY_V1 = VALIDATED_DIAGNOSTIC_WITH_SELECTION_BIAS

G1 = EN CURSO
G2 = NOT YET EVALUATED
```

### Recommended next step

The diagnostic phase has now done its job.

Proceed to:

```text
F3.1 — D_GEN model-design freeze
```

before fitting anything.

That substep should define, in order:

```text
Participation
-> TripCount
-> activity/purpose chain
-> Timing
-> DistancePrior
```

with TRAIN/CALIBRATION/TEST roles and ablations fixed in advance.
