# F1-P_CONSTR-CAL-01 — Commit-bound CAL Authorization PREOPEN v1

**Required parent:** `83df51a035d21621b9c5b8de04b6f03ea1a78174`

## Decision

This artifact authorizes the **future controlled runner** to read only the frozen CALIBRATION partition for F1-P_CONSTR-CAL-01.

The authorization is bound exactly to the PRE-CAL Entry Gate commit above. A runner based on any other lineage must fail closed.

## What changes here

```text
calibration_authorized = true
required_precal_commit = 83df51a035d21621b9c5b8de04b6f03ea1a78174
allowed_partition       = CALIBRATION_ONLY
```

## What does not happen here

```text
CAL rows read          = 0
candidate selection    = NONE
g1_thresholds_v1       = NOT_FROZEN
CAL reader             = NOT PRESENT
MiD TEST               = DO NOT READ
1000A-1035             = UNREAD
PLR                    = NOT PERFORMED
F3                     = UNTOUCHED
```

The original authorization template remains frozen and unchanged. This authorization is a new explicit artifact rather than a mutation of the template.

## Next step after commit + push

MAIN may prepare a separate CAL runner. That runner must verify the exact authorization commit, fail closed on mismatch, restrict inputs to CALIBRATION_ONLY, record source hashes and observed CAL household count, and generate a RunBundle before any candidate winner or numeric `g1_thresholds_v1` values are frozen.

## Traceability wording

Authorization applies only to the controlled project lineage. It does not claim that no person manually inspected CAL outside the controlled workflow.
