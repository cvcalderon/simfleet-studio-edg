# F3.4a — Required RunBundle specification

Each controlled component CAL run must return a compact auditable bundle. Large evidence tables may remain local, but hashes and row counts must be recorded.

## Required files

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
checksums.sha256
```

For DG_PARTICIPATION also require:

```text
part_b_calibration_decision.json
selected_component_artifact.json
```

## Evidence requirements

The run manifest must state exact CAL files opened and exact rows read. TEST files opened/rows read must remain zero.

Candidate evidence must retain component, artifact_id, grid_id, role, evaluation mode, replicate id where applicable, evaluation person id, household id, event index, draw index, seed, weight and canonical observed/generated payload provenance.

## Stop rule

After the component decision is materialized and checksummed, execution stops. No next component may run until MAIN reviews and freezes the selected upstream artifact.
