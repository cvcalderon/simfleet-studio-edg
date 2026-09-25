# R6 implementation note v1 — D_MATCH_FULLDAY_V1

## Scope

R6 reproduces only the `D_MATCH_FULLDAY_V1` branch that remained pending after accepted R5. It also reconstructs the historical combined F2.1 bridge validation and bridge hash from the exact R5 replay artifacts plus the R6 match artifacts.

R6 does not execute F2.2/R7 metrics and does not start `D_GEN`/F3.

## Frozen matching behavior

Each generated M-scale person is assigned one complete strict-TRAIN source diary from the accepted R5 full-day donor pool.

Candidate matching tiers are evaluated in this fixed order:

1. age + sex + primary activity + household size;
2. age + sex + primary activity;
3. age + sex + employment participation;
4. age + sex;
5. age;
6. global fallback.

Within a non-empty tier, source diaries are sampled with probability proportional to `P_GEW` using NumPy `default_rng(20260924)`.

The generated person's own source `HP_ID` is excluded. If a tier contains only the self diary, R6 relaxes to the next tier instead of degrading into replay.

## Matching inputs allowed

Only static M1 attributes participate in similarity:

- `age_infr_class`;
- `sex`;
- `primary_activity_status`;
- `employment_participation`;
- `household_size_class`.

The following are forbidden as matching features:

- participation outcome;
- trip count;
- purpose;
- timing;
- distance;
- observed/chosen mode;
- execution outcome.

Purpose, timing and diagnostic distance evidence enter only after a complete diary donor has been selected.

## Frozen anchors

Expected person-day results:

- matched person-days: 100,000;
- complete zero-trip: 15,574;
- complete mobile: 84,426;
- trip intents: 291,508;
- self diary matches: 0;
- global fallback: 0.

Expected tiers:

- T1: 94,322;
- T2: 3,929;
- T3: 1,535;
- T4: 214;
- T5: 0;
- T6: 0.

## Historical witness

The recovered handoff retained the historical combined F2.1 bridge SHA-256:

`2711e5542302f4c1b3b28ee8dab8b19bc044f0c61a143645e165aa32f5d437b5`

The individual historical SHA-256 values of the two D_MATCH CSVs were not retained. R6 therefore records their newly reproduced hashes but requires the combined bridge hash to match exactly. Because the two R5 replay inputs are already byte-exact historical witnesses, this is the strongest recovered cryptographic witness for the D_MATCH pair.

## Combined F2.1 validation

R6 reconstructs the historical 20-check bridge suite across R5 + R6, including:

- replay identity and TRAIN-only provenance;
- complete matched-day coverage;
- strict-TRAIN D_MATCH donors;
- zero self match;
- no global fallback;
- age/sex preservation;
- trip-count equality;
- zero-trip semantics;
- temporal/purpose/distance completeness;
- no mode leakage;
- no `km_routing` prior;
- M3/M5 downstream boundaries.

## Gate semantics

R6 is a PRE-G1 diagnostic reproduction stage. It does not close G1 or G2. D_MATCH remains diagnostic and is not `D_GEN`.
