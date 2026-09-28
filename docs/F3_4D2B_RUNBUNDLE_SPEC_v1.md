# F3.4d-2b RunBundle specification

A successful authorized run materializes at least:

- `run_manifest.json`
- `execution_authorization_snapshot.json`
- `execution_contract_snapshot.yaml`
- `cal_access_manifest.json`
- `input_hash_validation.csv`
- `candidate_artifact_validation.csv`
- `primary_metrics.csv`
- `isolated_guardrail_candidate_metrics.csv`
- `isolated_guardrails.csv`
- `bootstrap_intervals.csv`
- `grid_selection.csv`
- `promotion_decisions.csv`
- `propagated_guardrail_candidate_metrics.csv`
- `propagated_guardrails.csv`
- `upstream_selection_snapshot.json`
- `selected_component_artifact.json`
- `purpose_attribution_snapshot.json`
- `validation.csv`
- `issues.csv`
- `performance.json`
- `environment.json`
- `evidence_manifest.json`
- `stochastic_evidence.csv.gz` when evidence materialization is enabled
- `checksums.sha256`

The runner writes to `<RunBundle>.partial` and atomically renames only after
success. On failure, `.partial/failure.json` and fresh checksums are preserved.
No failure handler may delete partial evidence.
