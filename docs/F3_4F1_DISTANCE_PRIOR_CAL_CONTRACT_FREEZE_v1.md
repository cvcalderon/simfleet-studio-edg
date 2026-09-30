# F3.4f-1 — Distance Prior CAL Contract Freeze

This phase freezes Distance Prior CAL semantics only. It reads **zero** Distance CAL rows.

## Candidate universe
Exactly five TRAIN-fitted, unselected artifacts are admissible:
`DIST_REF_REFERENCE`, `DIST_A_DA1`, `DIST_B_DB1`, `DIST_B_DB2`, `DIST_B_DB3`.

## Future CAL inputs
Only the frozen CAL files are admissible:

- `person_day_context.csv`: 469 rows;
- `distance_raw.csv`: 1,147 rows;
- `distance_expanded_sensitivity.csv`: 1,257 rows.

Total physical rows across files = 2,873. Contract-phase CAL rows read = 0.

## Primary
`M2-DIST-01`: weighted 1-D Wasserstein distance in km against raw `wegkm`, with `W_GEW` on source evidence. Lower is better. Candidate point score is the arithmetic mean of the metric computed independently across 32 paired CRN replicates. Practical promotion margin = **0.25 km**.

## ISOLATED
All 1,147 raw-distance rows remain in scope. Upstream state is empirical CAL and teacher-forced **only for component evaluation**. Missing time context and unresolved transition context are preserved and handled with the already-frozen missing/backoff semantics; no row may be silently removed.

`source_trip_id` is identity/provenance only. It may participate in the deterministic RNG identity but is never a predictor.

## Distance summary evidence
The preregistered Distance summary evidence is `MEAN`, `P50`, `P90`, `P95` plus `M2-DIST-02` sensitivity.

The only frozen distance-summary worsening tolerance is `DIST_QUANTILE_ABS_ERROR_KM = 0.50 km`, explicitly associated with `P50/P90/P95`. Therefore:

- P50/P90/P95: decision-driving guardrails, max worsening 0.50 km each;
- MEAN: mandatory report-only evidence, no post-hoc numeric threshold;
- M2-DIST-02: report-only sensitivity.

No new mean threshold is introduced after prior CAL inspection.

## PROPAGATED
After provisional ISOLATED selection, fixed MAIN-frozen upstream artifacts generate state in order:

`PA1 -> COUNT_REF -> CHA2 -> TIME_B_TB2 -> Distance`.

Distance is generated for every generated trip. PROPAGATED is a **hard runtime-admissibility check only**:

- zero structural/runtime generation failures;
- generated distances finite and strictly positive;
- zero NoFutureInformation violations;
- no `km_routing`, mode, route or execution outcome consumption;
- no candidate/replicate-specific cohort reselection.

PROPAGATED does not redefine the primary metric and does not reselect candidates. A source-`W_GEW` mapping to a variable number of generated trips was never preregistered; defining one now would alter metric semantics after CAL inspection. Full-pipeline generated-trip weighting must be frozen separately before the later joint CAL gate.

This is consistent with the F3.1c rule that isolated gains cannot proceed through a hard propagated failure and with the precedent of Time Schedule's propagated hard-invariant gate.

## Stochastic protocol

- 32 paired common-random-number replicates;
- master seed `20260926`;
- 1,000 paired household bootstrap replicates;
- 95% percentile CI;
- candidate identity excluded from the RNG key.

ISOLATED trip identity uses `context_row_id + source_trip_id`; PROPAGATED uses `context_row_id + generated_trip_index`.

## Selection
Within a family: hard pass -> thresholded guardrails pass -> lowest primary metric -> lexical grid-id tie-break.

Sequential complexity order:
`REFERENCE_BASELINE < CORE_CANDIDATE_A < CORE_CHALLENGER_B`.

Promotion requires:

1. hard pass;
2. primary point improvement >= 0.25 km;
3. paired household-bootstrap CI95 lower endpoint > 0;
4. P50/P90/P95 worsening <= 0.50 km each.

MEAN and M2-DIST-02 remain report-only and cannot drive promotion.

## Implementation
A dedicated Distance Prior real-CAL runner is required. The generic F3.3c harness is not used directly because `DistancePriorAdapter` does not expose `required_columns` and propagated Distance state construction is component-specific. F3.4f-1 changes no model/adapter behavior.

## Boundaries
Candidate selection = NONE. Distance real CAL = NOT_AUTHORIZED. TEST = SEALED. G2 = NOT_EVALUATED. Joint CAL gate = NOT_AUTHORIZED.
