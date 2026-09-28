# F3.4c-1 — Trip Count CAL Contract Freeze

This phase freezes the component-specific interpretation needed to evaluate
`DG_TRIP_COUNT` without changing the already-frozen F3.1c/F3.4a protocol.

## Candidates

Five TRAIN-fitted artifacts enter unchanged:

- `COUNT_REF / REFERENCE`
- `COUNT_A / CA1`
- `COUNT_A / CA2`
- `COUNT_A / CA3`
- `COUNT_B / CB1`

No candidate is selected in F3.4c-1.

## Upstream state

Participation is no longer unresolved. The only allowed generated upstream
participation artifact is the MAIN-frozen:

`DG_PARTICIPATION::PART_A::PA1`.

## ISOLATED mode

ISOLATED is the candidate-selection mode.

Empirical CAL participation is teacher-forced only for evaluation, never runtime.
The proper primary score is weighted discrete CRPS on positive K and is computed on
the frozen 381-row CAL positive-trip-count universe.

For generated-outcome guardrails, the 460-row participation universe is reconstructed
as person-days: empirical NoTrip days contribute K=0; empirical mobile days receive
a candidate trip-count draw. Metrics are computed per stochastic replicate and then
averaged over the frozen 32 replicates.

## PROPAGATED mode

PROPAGATED is not a second primary-selection surface. It is the mandatory
post-selection pipeline check.

For each replicate, the frozen PA1 participation artifact generates TripDay on the
460 CAL participation person-days. The same PA1 draws are shared across all trip-count
candidate comparisons. On generated mobile days, the Trip Count artifact draws K from
its positive-count PMF.

Because generated mobile status can differ from the observed mobile status, the
conditional positive-count CRPS is not redefined on this generated subset. PROPAGATED
therefore checks generated-outcome guardrails only.

If the provisional ISOLATED winner fails the propagated guardrail check, MAIN freeze
is blocked. There is no automatic fallback or post-CAL threshold change.

## Frozen guardrails

- M2-COUNT-01: absolute error in weighted mean trips/person/day; worsening tolerance 0.10.
- M2-COUNT-02: TVD of weighted `0..11,12+` trip-count distribution; worsening tolerance 0.005.
- M2-CHAIN-01: TVD of trips/mobile-day distribution; worsening tolerance 0.005.
- M2-COND-02: maximum supported-subgroup absolute error in E[Trips/day], for age, sex,
  primary activity, and household-size class; `source_n < 30` is report-only;
  worsening tolerance 0.02.

F3.4c-1 reads no new Trip Count CAL rows, keeps TEST sealed, and does not evaluate G2.
