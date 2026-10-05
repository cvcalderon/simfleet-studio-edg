# F1-P_CONSTR-CAL-01 — PRE-CAL Entry Gate v1

**Required parent:** `cf4eff1544d2c3fc16d5d0039d6d2f2136a264a4`

## Purpose

This gate is the final repository-level barrier before a **separate, commit-bound authorization** may permit the first controlled F1 read of the CALIBRATION partition.

It does **not** authorize CAL and it contains no CAL reader.

## Required state

```text
branch                 = main
HEAD                    = origin/main
worktree before overlay = clean
CAL authorized          = false
CAL rows read           = 0
candidate selection     = NONE
g1_thresholds_v1        = NOT_FROZEN
MiD TEST                = DO NOT READ / G2 CLOSED
1000A-1035              = UNREAD
PLR allocation          = NOT PERFORMED
F3                      = UNTOUCHED
G1                      = OPEN
```

The following previously frozen artifacts must remain byte-identical:

- CAL-01 PREOPEN config;
- authorization template;
- evaluation contract;
- threshold rule;
- I/O-free calibration evaluation module.

## Authorization discipline

A PASS here still does not authorize CAL. The Entry Gate itself must first be committed and pushed. MAIN may then create a new authorization artifact whose `required_precal_commit` is exactly that Entry Gate commit.

No authorization may be bound retroactively to `cf4eff...`; it must bind to the actual Entry Gate commit produced after this PREOPEN passes.

## Traceability caveat

The gate verifies the controlled Git/project lineage: no CAL authorization is active and no CAL reader is introduced by this lineage. It cannot establish that no person has ever opened CAL data manually outside the controlled workflow. Project claims must use the narrower controlled-lineage wording.
