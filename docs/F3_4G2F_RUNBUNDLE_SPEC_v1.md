# F3.4g-2f — Held-out TEST RunBundle specification v1

Required top-level evidence:

- `run_manifest.json`
- `authorization_snapshot.json`
- `contract_snapshot.json`
- `holdout_consumption.json`
- `source_hash_validation.csv`
- `test_materialization_manifest.json`
- `test_row_counts.csv`
- `test_vocabulary_application.json`
- `pipeline_artifact_validation.csv`
- `generated_days.csv`
- `generated_trips.csv`
- `test_metrics.csv`
- `g2_decision.json`
- `validation.csv`
- `issues.csv`
- `environment.json`
- `checksums.sha256`

Required nested evidence:

`materialized_test/`

containing exactly the eight frozen TEST tables.

The RunBundle verifier accepts either scientific `G2=PASS` or `G2=FAIL` as a
valid execution outcome when integrity checks pass.

A `.partial` bundle after source-content I/O is terminal evidence for that
holdout version and must be preserved.
