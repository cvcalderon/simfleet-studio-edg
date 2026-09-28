# F3.4d-2b-R1 — Activity Chain PRE-CAL Semantic/Input Remediation

This phase closes three PRE-CAL ambiguities without reading CAL.

## AC-CAL-INPUT-001
The future real-CAL runner may open exactly:
- person_day_context.csv: 469 rows;
- chain_days.csv: 319 rows;
- chain_transitions.csv: 1065 rows.
Total physical rows: 1853.

## AC-PURPOSE-SEM-001
Activity Chain predicts destination activity, but M2-PURP-01 evaluates canonical
trip purpose. TRAIN proves:
- RETURN_PREVIOUS always returns to prefix_second_last_activity;
- every non-RETURN_PREVIOUS purpose equals the frozen direct destination mapping.

CHAIN_PURPOSE_ATTRIBUTION_V1 therefore uses the direct mapping plus one binary
RETURN_PREVIOUS decision only on return-eligible transitions. The Bernoulli
probability is TRAIN-only weighted MLE, raw source_n >= 30, with L1-L4 backoff
and a global return-eligible fallback. No smoothing and no CAL-tuned parameter
are introduced. The primitive is identical for all six candidates.

Frozen TRAIN anchors include 4872 transitions, 53 RETURN_PREVIOUS rows, 1575
return-eligible rows, global weighted probability 0.029805493179307727, zero
semantic violations, and selected backoff rows 780/184/405/175/31.

## AC-PROP-OBS-001
PROPAGATED fixes the source cohort to the 319 chain-observable CAL person-days.
PA1 and COUNT_REF generate upstream state inside that cohort; the cohort is not
reselected from generated mobility.

M2-PURP-01 and M2-TRANS-01 use generated transitions. NoTrip contributes zero
transitions. M2-RET-01 keeps its frozen denominator of functional mobile days;
generated NoTrip days are excluded from that denominator, not coerced to
return_home=false. Zero denominator is a HARD failure.

Primary next-activity log-loss remains ISOLATED-only on 1065 observed
transitions.

All candidate families, margin 0.01, 32 CRN replicates, 1000 household
bootstraps, guardrail tolerances, TEST seal, and G2 state remain unchanged.
