# F3.4e-2b — Time Schedule Real-CAL Runner PRE-OPEN

## Scope

This overlay implements the official controlled real-CAL runner for
`DG_TIME_SCHEDULE` while keeping CAL closed during PRE-OPEN validation. It
extends the frozen F3.4e-1 Time Schedule CAL contract and follows the already
validated F3.4e-2a synthetic engineering smoke.

## Irreversible-I/O boundary

The real runner MUST validate an external authorization JSON before opening any
CAL file **and before creating the `.partial` RunBundle directory**. The
authorization is bound to the exact committed implementation HEAD, requires a
clean synchronized `main`, permits exactly two CAL files, leaves TEST sealed,
and does not authorize Distance Prior real CAL.

PRE-OPEN verification and focused tests read zero CAL rows.

## Frozen CAL inputs

A later commit-bound authorization may open only:

- `person_day_context.csv`: 469 rows;
- `time_trips.csv`: 1243 rows.

Physical rows opened: 1712.

The propagated fixed cohort is exactly the 378 unique `context_row_id` values
already represented in `time_trips.csv`. It is never reselected according to
generated mobility state.

## Candidate universe

Exactly seven frozen TRAIN artifacts enter unselected:

- `TIME_REF_REFERENCE`;
- `TIME_A_TA1`, `TIME_A_TA2`, `TIME_A_TA3`;
- `TIME_B_TB1`, `TIME_B_TB2`, `TIME_B_TB3`.

All must remain `FITTED_TRAIN_ONLY_NOT_SELECTED` at entry.

## ISOLATED evaluation

All 1243 CAL time rows remain in scope; no unresolved-transition row is silently
dropped. External upstream state is empirical CAL. The previous temporal prefix
is teacher-forced from the empirical row.

The boolean `trips_remaining_after_current` control follows the frozen semantic
mapping rather than assuming `source_trip_id` is an ordinal:

- SINGLE/LAST -> 0;
- FIRST/MIDDLE -> 1.

For every candidate and each of 32 CRN replicates the runner generates a planned
departure/duration pair. Candidate identity is absent from the time RNG key.

Primary score:

`M2-TIME-01 = weighted departure-hour distribution TVD`, mean over 32 paired CRN
replicates, W_GEW, lower is better.

Hard invariant:

`TEMPORAL_INVARIANT_VIOLATIONS = 0`.

Auxiliary report-only metric:

`CIRCULAR_WASSERSTEIN_DEPARTURE_MINUTES`.

## Selection

No composite score.

1. Within TIME_A choose the lowest primary metric among hard-pass grids.
2. Compare the best TIME_A against the current incumbent.
3. Within TIME_B choose the lowest primary metric among hard-pass grids.
4. Compare the best TIME_B against the resulting incumbent.

Promotion requires all of:

- temporal hard invariants pass;
- point improvement >= 0.005;
- paired 1000-household-bootstrap CI95 lower bound strictly > 0.

An empty eligible family produces no promotion decision and retains the current
incumbent.

## PROPAGATED evaluation

Only the reference and provisional isolated incumbent enter PROPAGATED.
The source cohort remains the fixed 378 CAL person-days.

Frozen upstream artifacts:

- `DG_PARTICIPATION::PART_A::PA1`;
- `DG_TRIP_COUNT::COUNT_REF::REFERENCE`;
- `DG_ACTIVITY_CHAIN::CHAIN_A::CHA2`.

Participation, trip count and activity chain are generated first. Time is then
generated sequentially; each generated arrival becomes the next temporal prefix.
A generated NoTrip contributes zero generated time trips but the source person-day
remains in the fixed cohort.

PROPAGATED is **hard-guardrail-only** and never redefines M2-TIME-01 selection.
Both reference and provisional incumbent must preserve zero temporal invariant
violations. A propagated failure blocks the selection proposal and returns to
MAIN.

## Boundaries

PRE-OPEN state:

- CAL rows read: 0;
- candidate selection: NONE;
- real Time Schedule CAL execution: unauthorized;
- Distance Prior real CAL: unauthorized;
- TEST: SEALED;
- G2: NOT_EVALUATED.
