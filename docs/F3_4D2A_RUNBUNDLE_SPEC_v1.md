# F3.4d-2a synthetic RunBundle

Expected files:

- `run_manifest.json`
- `execution_contract_snapshot.yaml`
- `candidate_artifact_validation.csv`
- `synthetic_primary_metrics.csv`
- `synthetic_guardrails.csv`
- `synthetic_bootstrap_check.json`
- `crn_validation.json`
- `validation.csv`
- `environment.json`
- `evidence_manifest.json`
- `checksums.sha256`

Required semantics:
- `execution_mode = SYNTHETIC_TRAIN_PREOPEN`
- `candidate_artifacts = 6`
- `candidate_selection = NONE`
- `cal_read_performed = false`
- `cal_files_opened = []`
- `cal_rows_read = 0`
- `real_cal_open_authorized = false`
- `test_rows_read = 0`
- `test_open_authorized = false`
- `formal_g2 = NOT_EVALUATED`.

The RunBundle must be written outside the repository.
