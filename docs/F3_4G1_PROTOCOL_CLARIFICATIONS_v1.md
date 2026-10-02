# F3.4g-1 — Joint CAL protocol clarifications v1

Status: `FROZEN_BEFORE_JOINT_PIPELINE_OUTPUTS_ARE_COMPUTED`.

These clarifications operationalize the already-frozen F3.1c/F3.3/F3.4a Joint
gate. They introduce no candidate, feature, hyperparameter, seed, CAL partition,
TEST access, or new numeric threshold.

## C1 — Proper-score primaries are not redefined on propagated state

The accepted component contracts explicitly state that:

- Trip Count CRPS is not redefined on generated-mobile propagated rows;
- Activity Chain next-activity log-loss is not redefined in PROPAGATED;
- Time PROPAGATED is a hard/runtime surface rather than a second selection surface.

Therefore the Joint gate does not invent new propagated targets for Participation
log-loss, Trip Count CRPS or Activity Chain log-loss.

The criterion `selected_component_dominated` is instead witnessed from the five
already-accepted MAIN freezes in `F3_4G1_PRIMARY_EVIDENCE_WITNESS_v1.csv`.

## C2 — Joint material degradation is an end-to-end generated-outcome comparison

Both pipelines are generated end-to-end from static CAL person-day context with
the same 32 CRN replicate schedule. Decision-driving generated-outcome metrics
reuse the exact metric definitions, denominator semantics and LOW_N rules already
accepted in the component CAL contracts.

For each metric:

`worsening = selected_pipeline_error - all_reference_pipeline_error`.

The metric passes when `worsening <= frozen max_worsening`.

Report-only metrics are recorded but cannot fail the Joint gate.

## C3 — Distance W1 materiality uses an existing preregistered number

F3.1c froze `DIST_W1_KM = 0.25 km` as the Distance primary practical
materiality magnitude. The Joint protocol requires that no primary/guardrail
metric materially degrade the all-reference pipeline, but did not duplicate
that number in a separate `max_worsening` field.

For Joint `M2-DIST-01` only, `0.25 km` is reused as the maximum material
worsening. This is a semantic reuse of a preregistered value, not a new numeric
threshold.

Distance MEAN remains `REPORT_ONLY_UNTHRESHOLDED`; P50/P90/P95 retain `0.50 km`;
M2-DIST-02 remains report-only.

## C4 — Metric-specific denominator semantics are retained

The generation universe is the 469-row CAL person-day context. Each metric uses
the already-frozen evaluable source cohort/denominator from its accepted
component contract. No new complete-case intersection across all five
components is created.

## C5 — PASS semantics

The later real Joint gate passes only if:

1. both pipelines have zero required structural/temporal/NoFutureInformation
   violations;
2. `selected_component_dominated = false`;
3. no decision-driving Joint metric exceeds its frozen worsening tolerance;
4. all five selected artifact identities/manifests remain frozen and exact;
5. no post-CAL candidate/feature/threshold/hyperparameter change is detected.

A PASS may make held-out TEST **eligible for a later explicit authorization**.
F3.4g-1 itself does not open TEST and does not close G2.
