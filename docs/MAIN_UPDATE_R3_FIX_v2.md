# MAIN update — R3 corrective patch v2

## Current state

- R0: SUPERADO
- R1: SUPERADO
- R2: SUPERADO
- R3 official attempt #1: FAIL / PRESERVED
- R3 root cause: IDENTIFIED
- R3 corrective patch: READY FOR LOCAL QUALITY GATES
- R4–R7: PENDING
- G1: OPEN
- G2: NOT CLOSED

## Defect

`source_person_id` was materialized from MiD `P_ID` (local roster/member index) instead of `HP_ID` (global source-person reference).

## Patch scope

Only identity/provenance handling and regression tests are changed. No scientific algorithm or frozen witness is modified.

## Required next steps

1. Apply patch overlay.
2. Run full pytest, Ruff and `verify_r3_prep.py`.
3. Commit and push the fix.
4. Preserve `R3_ptrs_s_v1` FAIL untouched.
5. Execute the corrected official retry into a new directory, e.g. `R3_ptrs_s_v1_retry01`.
6. Audit that retry independently before closing R3.
