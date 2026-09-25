# R6 assignment-witness fix v2

## Purpose

Correct R6 reproduction after attempt01 demonstrated that the original F2.1 stochastic donor-selection mechanics were under-specified at implementation level.

## New frozen witness

`configs/reproduction/reference/r6_historical_assignment_witness_v1.csv`

Columns:

- `generated_person_id`
- `diary_source_hp_id`

SHA-256:

`55a0a37fd9fea048f4b8e1f8c042a10d09b0b5cf5c749e34fca3d61f77268494`

The witness has 100,000 rows and contains no trip count, purpose, time, distance, mode or execution outcome.

## Exact historical hashes recovered

- D_MATCH person-days: `d908ce562f2d14de017d369aab61f3d96e998b4f19f1d8753c1820c2c799a65e`
- D_MATCH trips: `7d3617811aef04ca6e83c15e2bc64643e2fe6a7a922bd51103fc9ca7073606b6`
- combined F2.1 bridge: `2711e5542302f4c1b3b28ee8dab8b19bc044f0c61a143645e165aa32f5d437b5`

## Reproduction semantics

Retry01 recomputes the matching support tier for every generated person and validates that the witnessed donor:

1. belongs to the frozen complete strict-TRAIN donor pool;
2. belongs to the first admissible matching tier;
3. is not the generated person's own source diary;
4. respects the static-feature-only matching contract.

The resulting person-day and trip files are required to match their historical SHA-256 values exactly.

## Limitation

`R6-RNG-PROVENANCE-001`: the exact original RNG API and candidate-order mechanics were not preserved. Retry01 therefore proves exact historical output reconstruction from frozen assignment evidence, not algorithmic regeneration of the original random draw.
