# F3.4g-2c — Joint Real-CAL RunBundle specification v1

Required evidence:

- `run_manifest.json`
- `authorization_snapshot.json`
- `contract_snapshot.json`
- `cal_access_manifest.json`
- `input_validation.csv`
- `pipeline_artifact_validation.csv`
- `generated_days.csv`
- `generated_trips.csv`
- `joint_metrics.csv`
- `joint_gate.json`
- `validation.csv`
- `issues.csv`
- `environment.json`
- `checksums.sha256`

Required audit properties:

- exact implementation commit;
- 8 exact CAL files;
- 6,341 total physical CAL rows, each physical file read once;
- 10 exact frozen artifact slots;
- 32 CRN replicates per pipeline;
- no candidate selection;
- no TEST reads;
- explicit scientific Joint PASS/FAIL separate from runner PASS/FAIL;
- all decision-driving metrics traceable to the frozen F3.4g-1 matrix.
