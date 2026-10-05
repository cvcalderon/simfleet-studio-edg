# F1-P_CONSTR-CAL-01 PREOPEN v1

**Required parent:** `45c6f10f4168e26fd6929b245adf505a3b2f1584`

## Purpose

Freeze the F1 population CAL evaluator, materiality-threshold derivation rule, selection logic and authorization schema without reading CAL.

## Explicitly not authorized

- reading MiD CAL household/person rows;
- reading MiD TEST;
- reading `1000A-1035`;
- selecting P_TRS/HD_U/HD_W;
- freezing numeric `g1_thresholds_v1`;
- PLR allocation;
- F3 changes.

## Expected PREOPEN result

Focused synthetic tests and verifier establish that evaluation/selection primitives are deterministic, household-atomic and data-I/O-free. A successful commit still does **not** authorize CAL. A separate commit-bound authorization step must follow.
