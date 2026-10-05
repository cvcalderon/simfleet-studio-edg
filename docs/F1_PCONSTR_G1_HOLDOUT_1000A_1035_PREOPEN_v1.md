# F1-P_CONSTR-G1-HOLDOUT-1000A-1035 PREOPEN v1

Parent: `e2cd5e4445b3c75af865d4a1d43509a0b7953b48`

This subphase freezes the non-value semantics and pure metric implementation for the external senior-status feature holdout. It **does not authorize acquisition or reading of 1000A-1035 values**.

Frozen upstream state:

- `F1-P_CONSTR-CAL-01 = CLOSED / FROZEN`;
- selected candidate = `P_CONSTR_RMIN_V2_HD_U`;
- `g1_thresholds_v1 = FROZEN`;
- MiD TEST = consumed by G2 / do not reopen;
- G1 remains OPEN;
- G2 remains CLOSED / DO NOT REOPEN.

Two blockers remain before any holdout-value authorization:

- `HOLD-THRESH-001`: exact numeric pass/fail threshold rule for the two senior decision metrics is not yet frozen;
- `HOLD-MREAL-001`: the selected candidate must be materialized and frozen at M scale using the already-frozen seeds.

Until both are resolved, `1000A-1035` acquisition/read remains forbidden.
