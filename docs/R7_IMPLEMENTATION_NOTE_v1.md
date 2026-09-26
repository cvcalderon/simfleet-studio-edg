# R7 — F2.2 diagnostic reproduction — implementation note v1

## Objective

Reproduce the frozen F2.2 diagnostic validation of `D_REPLAY_EXACT_V1` and
`D_MATCH_FULLDAY_V1` from accepted PRE-F3 artifacts.

R7 is diagnostic. It does **not** close G2, does not define final G2 numeric
thresholds, and does not consume TEST outcomes.

## Accepted upstream inputs

- R2 strict household split.
- R4 `P_TRS_EXP_V1_M` persons and households.
- R5 accepted `D_REPLAY_EXACT_V1` outputs and full-day donor pool.
- R6 accepted `D_MATCH_FULLDAY_V1` outputs from `retry01`.
- Frozen F0.3 person-day, purpose/transition, time and spatial eligibility evidence.
- Raw MiD Personen only for strict-TRAIN person weights/static attributes.

Every input is SHA-256 checked before the run is accepted.

## Metric contract

Primary reference population is strict TRAIN. Person-day metrics use `P_GEW`;
trip metrics use `W_GEW`.

The frozen metric families are:

- participation;
- trip count and mobile chain length;
- purpose;
- departure time;
- return-home;
- activity transitions;
- raw and expanded source-distance diagnostics;
- conditional participation/trip count on static M1 dimensions;
- complete-diary selection bias;
- donor concentration.

`km_routing` and mode metrics are excluded. Cells below source `n=30` are flagged
`LOW_N`; they are not silently pooled.

## Historical witness policy

Eleven F2.2 historical artifacts are retained under
`configs/reproduction/reference/f2_2_historical/`.

Ten are required byte-exact. `simfleet_edg_F2_2_global_metrics_v1.csv` is required
numerically equivalent at `atol=1e-12`. Local reconstruction showed a maximum
absolute difference of approximately `1.19e-13`, caused by floating-point
serialization/arithmetic, while all metric semantics and values reproduce.

This is recorded as numeric equivalence rather than replacing the recomputed file
with the historical CSV.

## Frozen historical anchors

Selected anchors include:

```text
strict TRAIN person-days                    2,200
REF_TRAIN_BINARY                            2,154
REF_TRAIN_CORE_STRICT_COUNT                 2,052
REF_TRAIN_DIRECT_PURPOSE                    6,134
REF_TRAIN_DIRECT_TIME_VALID                 6,103
REF_TRAIN_TRANSITION                        5,812
REF_TRAIN_DISTANCE_RAW                      5,617
REF_TRAIN_DISTANCE_EXPANDED                 6,145
REF_TRAIN_FULL_FUNCTIONAL                   1,422
full-day donor pool                         1,658
D_REPLAY participation coverage            87,591
D_REPLAY count coverage                    82,873
F2.2 validation                              18/18
```

Key metric anchors:

```text
P(TripDay) strict TRAIN       0.8792475284865663
P(TripDay) D_REPLAY           0.8849996004155678
P(TripDay) D_MATCH            0.84426
mean trips strict TRAIN       3.190172808457594
mean trips D_REPLAY           3.261810239764459
mean trips D_MATCH            2.91508
purpose TVD replay/match      0.0363612473 / 0.0350592455
distance W1 replay/match km   2.7334370522 / 2.0135789541
unique D_MATCH donors         1,637
effective donors              1101.5343712871406
top-10 donor share            0.02721
```

## Interpretation

R7 separates:

1. exact replay fidelity;
2. complete-diary selection bias;
3. matching/weighting distortion;
4. finite donor reuse.

No diagnostic difference becomes an F2 pass/fail threshold.
