# F3.4e-2b RunBundle specification

A successful authorized run materializes at least:

- `run_manifest.json`
- `execution_authorization_snapshot.json`
- `execution_contract_snapshot.yaml`
- `cal_access_manifest.json`
- `input_hash_validation.csv`
- `candidate_artifact_validation.csv`
- `primary_metrics.csv`
- `isolated_auxiliary_metrics.csv`
- `isolated_temporal_guardrails.csv`
- `bootstrap_intervals.csv`
- `grid_selection.csv`
- `promotion_decisions.csv`
- `propagated_temporal_guardrails.csv`
- `upstream_selection_snapshot.json`
- `selected_component_artifact.json`
- `validation.csv`
- `issues.csv`
- `performance.json`
- `environment.json`
- `evidence_manifest.json`
- `stochastic_evidence.csv.gz` when evidence materialization is enabled
- `checksums.sha256`

The runner writes to `<RunBundle>.partial` and atomically renames only after
success. On failure after staging creation, `.partial/failure.json` and fresh
checksums are preserved. Invalid/missing authorization fails before CAL I/O and
before staging creation.
