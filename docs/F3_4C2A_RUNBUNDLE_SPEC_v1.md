# F3.4c-2a / F3.4c-2b RunBundle surfaces

The PRE-OPEN synthetic bundle exercises the same core plumbing while declaring zero
CAL/TEST access.

The future real F3.4c-2b bundle contains at least:

- run_manifest.json
- execution_contract_snapshot.yaml
- execution_authorization_snapshot.json
- environment.json
- cal_access_manifest.json
- input_hash_validation.csv
- candidate_artifact_validation.csv
- primary_metrics.csv
- isolated_guardrail_candidate_metrics.csv
- isolated_conditional_guardrails.csv
- isolated_guardrails.csv
- bootstrap_intervals.csv
- grid_selection.csv
- promotion_decisions.csv
- propagated_guardrail_candidate_metrics.csv
- propagated_conditional_guardrails.csv
- propagated_guardrails.csv
- upstream_selection_snapshot.json
- selected_component_artifact.json
- stochastic_evidence.csv.gz
- evidence_manifest.json
- validation.csv
- performance.json
- issues.csv
- checksums.sha256

A successful execution proposes a Trip Count selection but never freezes it in MAIN.

## F3.4c-2b-R1 count-observability clarification

For Trip Count, the CAL participation surface contains 460 person-days:
61 observed NoTrip and 399 observed TripDay. Only 381 TripDay rows have an
observable `target_trip_count`; the remaining 18 are `COUNT_TARGET_UNOBSERVED`.

Therefore:
- ISOLATED CRPS remains on 381 positive count-target rows.
- Count-based full-day guardrails use 442 person-days = 61 known NoTrip + 381
  TripDay with observable K.
- The 18 count-unobserved TripDay rows are excluded from Trip Count scoring and
  must never be coerced to K=0.
- Participation itself remains validated on its original 460-row surface.
