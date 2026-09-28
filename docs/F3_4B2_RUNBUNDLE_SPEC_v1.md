# F3.4b-2 — official Participation CAL RunBundle v1

Required core files:

```text
run_manifest.json
execution_contract_snapshot.yaml
execution_authorization_snapshot.json
environment.json
cal_access_manifest.json
input_hash_validation.csv
candidate_artifact_validation.csv
candidate_probabilities.csv
primary_metrics.csv
guardrail_candidate_metrics.csv
conditional_guardrails.csv
guardrails.csv
bootstrap_intervals.csv
grid_selection.csv
promotion_decisions.csv
validation.csv
performance.json
issues.csv
part_b_calibration_decision.json
selected_component_artifact.json
evidence_manifest.json
stochastic_evidence.csv.gz
checksums.sha256
```

The bundle must record exact CAL files/hashes/row counts and zero TEST access. Row-level evidence remains local; its checksum and row count are mandatory.

The bundle contains a proposal under frozen rules. It never authorizes DG_TRIP_COUNT by itself.
