# F3.4g-2b — External authorization schema v1

A future positive authorization must contain exactly the semantic fields
validated by `load_joint_real_cal_authorization()`.

Key values:

- phase: `F3.4g-2b`
- component: `DGEN_JOINT_PIPELINE`
- authorized implementation commit: exact synchronized current HEAD
- `joint_real_cal_open_authorized = true`
- `joint_gate_evaluation_authorized = true`
- 8 exact CAL filenames
- expected physical CAL rows: `6341`
- selected pipeline artifact count: `5`
- reference pipeline artifact count: `5`
- candidate selection at entry: `NONE`
- `test_open_authorized = false`
- `formal_g2 = NOT_EVALUATED`

The tracked template remains deliberately negative and cannot authorize a run.
