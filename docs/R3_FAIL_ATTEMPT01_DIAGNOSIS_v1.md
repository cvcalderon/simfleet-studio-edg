# R3 official attempt #1 — diagnosis v1

## Status

- Run: `R3_ptrs_s_v1`
- Git commit: `b1999fd71b6092d1c9a9ccda004e58bd8c5297df`
- Result: `FAIL`
- RunBundle TAR SHA-256: `6faaaed8238ad223b85a87afa8c602bdf8843f7a5f5ced02acb760937bd35885`
- Internal RunBundle checksums: all payloads verified `OK`.

The failed RunBundle must remain preserved and must not be overwritten or relabelled.

## Reproduced correctly

The attempt reproduced the frozen population mechanics and witnesses:

- source input hashes: 6/6 PASS;
- households: 5,663;
- persons: 10,000;
- resource relations: 64,263;
- linked Personen: 8,987;
- roster-only persons: 1,013;
- unique TRAIN donors used: 1,125;
- maximum donor reuse: 25;
- median donor reuse: 4.0;
- operational PLR target rows: 541;
- positive PLR targets: 540;
- household primary CSV: byte-exact;
- donor reuse audit: byte-exact;
- zone allocation audit: byte-exact.

## Root cause

The generated `persons` and `resources` tables differed only in `source_person_id` for linked Personen:

- `persons`: 8,987 differing cells, all in `source_person_id`;
- `resources`: 35,948 differing cells, all in `source_person_id`.

The implementation used `Personen.P_ID` as the source person identifier. In MiD B1, however:

- `P_ID` is the local household member index (1–6) for linked persons;
- `HP_ID` is the globally unique source-person reference.

The materializer therefore wrote values such as `1` where the frozen F1.3a output contains values such as `93627531`.

This is an implementation identity/provenance defect, not a donor-selection, spatial-allocation, demographic, enrichment-coverage or resource-cardinality defect.

## Corrective action

1. Keep `P_ID` for resolving `(H_ID, roster_slot)` in `load_person_lookup`.
2. Require `HP_ID` in `Personen` input.
3. Materialize `source_person_id` from `HP_ID`, not `P_ID`.
4. Add regression tests explicitly separating local `P_ID` from global `HP_ID`.

No scientific decision, seed, donor selection rule, split, target, population size or geography rule is changed.

## Expected effect

Historical primary hashes after the fix are expected to be:

- households: `2eb514ed76136263d64fa8a7e237a2fcbbd1deb360dc8d2cb9cfe2f1cc38c601`
- persons: `da3c22b2dd30f8e1a190d8c82a6df32254a91d33241cca6ff170a8d0d7f464c5`
- resources: `981a0c697bb61d8903480f6ef573037daa661e4e82f1c467989a3c91e04aedb4`

Their frozen snapshot digest is:

`f37ffeda502929bdda4c16f0c30d297fd6c2743b4c1e50e987471c6e714f9d01`

The preservation-TVD audit showed only machine-scale floating-point differences (~1e-16); it remains a REPORT_ONLY numeric witness and is not part of the root cause.
