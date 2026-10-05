# F1-P_CONSTR-G1 — 1000A-1035 AUTH-PREOPEN v1

## Purpose

Freeze the final authorization boundary for the external senior-status feature holdout **without acquiring or reading holdout values**.

## Frozen prerequisites

- candidate: `P_CONSTR_RMIN_V2_HD_U`;
- M realization: `RESOLVED_FROZEN`;
- M RunBundle SHA256: `00b440d58b2c4f7f5484e8260a43f1fb9f2ce69c0b5d5c23a6272aa3b2afa505`;
- exact senior metric implementation: frozen in the earlier `1000A-1035 PREOPEN` lineage;
- threshold rule: `MAX_FROZEN_CAL_TVD_MATERIALITY_TAU_V1`;
- numeric decision threshold: `0.0815667541845037`;
- candidate seed: `20261005`;
- H6 seed: `20261004`;
- holdout metric randomness: `NONE`.

## Decision rule

Both decision metrics must independently pass:

- `G1-HOLD-SEN-BERLIN-TVD <= 0.0815667541845037`;
- `G1-HOLD-SEN-BEZ-WTVD <= 0.0815667541845037`.

`G1-HOLD-SEN-BEZ-MAX` remains `REPORT_ONLY`.

There is no composite score.

## Authorization semantics

The repository contains only a **negative authorization template**. It does not permit value I/O.

After this AUTH-PREOPEN is committed and synchronized, MAIN may issue one external positive `A1` authorization bound to that exact commit. Only that external authorization may permit:

1. acquisition of `1000A-1035`;
2. reading its values;
3. evaluation of the already-frozen senior-status metrics.

## Immutable post-opening rules

After the first holdout value is read:

- candidate selection = `NONE`;
- threshold tuning = `FORBIDDEN`;
- same-lineage code tuning = `FORBIDDEN`;
- CAL reopen = `FORBIDDEN`;
- MiD TEST reopen = `FORBIDDEN`;
- failure requires a new experimental lineage.

## Current state

```text
G1 = OPEN
G2 = PASS_CLOSED_DO_NOT_REOPEN
HOLD-MREAL-001 = RESOLVED_FROZEN
HOLD-THRESH-001 = RESOLVED_FROZEN
1000A-1035 acquired = false
1000A-1035 values_read = false
1000A-1035 authorized = false
```
