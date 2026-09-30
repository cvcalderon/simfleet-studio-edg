# F3.4f-2b RunBundle specification

A successful authorized run materializes at least:
- `run_manifest.json`
- `execution_authorization_snapshot.json`
- `execution_contract_snapshot.yaml`
- `cal_access_manifest.json`
- `input_hash_validation.csv`
- `candidate_artifact_validation.csv`
- `primary_metrics.csv`
- `sensitivity_metrics.csv`
- `isolated_summary_metrics.csv`
- `isolated_guardrails.csv`
- `bootstrap_intervals.csv`
- `grid_selection.csv`
- `promotion_decisions.csv`
- `propagated_runtime_guardrails.csv`
- `upstream_selection_snapshot.json`
- `selected_component_artifact.json`
- `validation.csv`
- `issues.csv`
- `performance.json`
- `environment.json`
- `evidence_manifest.json`
- optional `stochastic_evidence.csv.gz`
- `checksums.sha256`

The runner writes to `<RunBundle>.partial` and atomically renames only after success. Invalid/missing authorization fails before CAL I/O and before staging creation. Failures after staging creation preserve `.partial/failure.json` plus fresh checksums.
