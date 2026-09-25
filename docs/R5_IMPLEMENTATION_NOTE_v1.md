# R5 implementation note v1 — D_REPLAY_EXACT_V1

## Scope

R5 reproduces only the `D_REPLAY_EXACT_V1` branch of historical F2.1 on the accepted `P_TRS_EXP_V1_M` population. It does not implement or execute `D_MATCH`; that is R6.

## Frozen behavior

Each generated person receives exactly one replay person-day row. If the generated person has a linked MiD `HP_ID`, replay uses only that same source person's Stichtag evidence. It never substitutes another diary. Roster-only generated members remain `UNAVAILABLE_NO_PERSONDAY`.

A replay mobile day is complete only when all three frozen evidence conditions hold:

1. `chain_coverage_status == DIRECT_REPORTED_CHAIN_COMPLETE`;
2. `full_functional_day_sequence_eligible == true`;
3. `temporal_sequence_fit_eligible == true`.

Incomplete states are preserved rather than repaired.

## M2 diagnostic TripIntent

TripIntent rows are materialized only for `COMPLETE_MOBILE_DAY`. They carry purpose/activity transition, timing and a diagnostic path-length prior. Raw `wegkm` is used when substantive; otherwise `wegkm_imp` is used with explicit imputed provenance. `km_routing` is never used.

The output deliberately does not contain exact destination, observed/chosen mode, feasible alternatives or execution outcome.

## Inputs

R5 consumes:

- accepted R4 persons;
- frozen R2 household split;
- raw MiD `Personen` for source-day metadata;
- frozen F0.3b/c/d/e evidence tables.

The F0.3 reference CSVs are byte-frozen under `configs/reproduction/reference/`.

## Exact historical witnesses

R5 requires byte identity for:

- D_REPLAY person-days: `bfaf6fef...95a5e`;
- D_REPLAY trips: `5c4fedaa...63698`;
- full-day donor pool: `1e2b0318...d34ab`.

Scalar anchors: 100,000 person-days, 65,963 complete, 194,457 trip intents, strict TRAIN pool 2,200 and full-day pool 1,658 = 261 zero-trip + 1,397 mobile.

## Gate semantics

R5 is a PRE-G1 diagnostic reproduction stage. It does not close G1 or G2. D_REPLAY is the explicit diagnostic exception to NoFutureInformation; its empirical future outcomes are not runtime inputs to `D_GEN`.
