# F3.4g-2a — Synthetic RunBundle specification v1

Required files:

- `run_manifest.json`
- `environment.json`
- `pipeline_artifact_validation.csv`
- `synthetic_person_day_context.csv`
- `seed_schedule.csv`
- `synthetic_generated_days.csv`
- `synthetic_generated_trips.csv`
- `synthetic_pipeline_summary.csv`
- `synthetic_metric_smoke.csv`
- `validation.csv`
- `issues.csv`
- `checksums.sha256`

Required properties:

- 10 pipeline artifact slots;
- 8 synthetic person-days;
- 32 stochastic replicates;
- 512 generated day rows (2 pipelines x 32 x 8);
- at least one generated trip in each pipeline;
- zero structural, temporal, distance and NoFutureInformation violations;
- identical CRN protocol across SELECTED and ALL_REFERENCE;
- `candidate_selection = NONE`;
- `joint_gate_evaluated = false`;
- `cal_rows_read = 0`;
- `test_rows_read = 0`.

The synthetic metric smoke is report-only and must contain
`decision_authorized = false`.
