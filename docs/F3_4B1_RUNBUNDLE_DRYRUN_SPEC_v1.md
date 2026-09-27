# F3.4b-1 synthetic RunBundle

The dry-run must materialize the same core evidence surfaces expected for the future controlled CAL run:

```text
run_manifest.json
execution_contract_snapshot.yaml
environment.json
cal_access_manifest.json
input_hash_validation.csv
candidate_artifact_validation.csv
primary_metrics.csv
guardrails.csv
bootstrap_intervals.csv
grid_selection.csv
promotion_decisions.csv
validation.csv
performance.json
issues.csv
part_b_calibration_decision.json
selected_component_artifact.json
checksums.sha256
```

Every file must clearly label the evidence as `SYNTHETIC_ONLY` or dry-run where relevant. `selected_component_artifact.json` must retain `candidate_selection = NONE` and `authorized_for_downstream = false`.
