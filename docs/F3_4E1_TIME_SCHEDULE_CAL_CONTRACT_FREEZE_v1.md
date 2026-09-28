# F3.4e-1 — Time Schedule CAL Contract Freeze

This phase freezes evaluation semantics only. It reads zero CAL rows.

## Candidate universe
Exactly seven TRAIN-fitted, unselected artifacts are admissible:
TIME_REF_REFERENCE, TIME_A_TA1, TIME_A_TA2, TIME_A_TA3,
TIME_B_TB1, TIME_B_TB2 and TIME_B_TB3.

## Future CAL inputs
Only `CALIBRATION/person_day_context.csv` (469 rows) and
`CALIBRATION/time_trips.csv` (1243 rows) are required: 1712 physical rows.

## Primary metric
`M2-TIME-01`: weighted departure-hour distribution TVD, W_GEW, hours 0..23.
The candidate score is the mean across 32 paired CRN replicates.
Lower is better; practical promotion margin = 0.005.

## Hard invariant
`TEMPORAL_INVARIANT_VIOLATIONS = 0` in ISOLATED and PROPAGATED.
Generation follows `REJECT_INVALID_DRAW_NO_SILENT_REPAIR`.

## ISOLATED
All 1243 time rows remain in scope. External upstream state is empirical CAL.
The previous temporal prefix is teacher-forced empirically.
For the adapter's boolean 'another trip remains' condition:
SINGLE/LAST -> 0, FIRST/MIDDLE -> 1.
This deliberately avoids assuming that source_trip_id is a numeric ordinal.

## PROPAGATED
The fixed cohort is the unique context_row_id set represented in CAL time_trips.
No candidate/replicate-specific cohort reselection is allowed.
PA1, COUNT_REF and CHA2 generate upstream state.
Time is then generated sequentially; the previous generated timing becomes
the next timing prefix. PROPAGATED is hard-guardrail-only and does not redefine
the primary selection metric.

## Auxiliary
`CIRCULAR_WASSERSTEIN_DEPARTURE_MINUTES` is report-only.

## Selection
Within TIME_A and TIME_B choose the lowest primary among hard-pass grids.
Promote REF->best A->best B only if hard invariants pass, point improvement
>=0.005 and paired-household bootstrap CI95 lower bound is strictly >0.
No composite score.

## Boundaries
CAL rows read = 0; candidate selection = NONE; Distance Prior real CAL is not
authorized; TEST remains sealed; G2 remains NOT_EVALUATED.
