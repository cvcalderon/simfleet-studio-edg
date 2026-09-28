# F3.4c-2c — Trip Count MAIN Freeze

## Decision

Freeze:

`DG_TRIP_COUNT::COUNT_REF::REFERENCE`

as the authoritative Trip Count component selection with target state
`MAIN_FROZEN`.

## Source evidence

The source execution is F3.4c-2b-A2, executed by implementation commit:

`372a6c03739f71b68c65c15c546a515f09830435`

The A2 RunBundle completed `PASS`.

Frozen CAL cardinalities:

- physical CAL rows read: 1310;
- Participation rows: 460;
- observed TripDay rows: 399;
- known NoTrip rows: 61;
- positive K-observed rows / ISOLATED CRPS rows: 381;
- `COUNT_TARGET_UNOBSERVED` positive TripDay rows: 18;
- count-based guardrail person-days: 442.

## Selection interpretation

The reference primary CRPS is:

`0.8931199056452576`.

All four non-reference artifacts failed the frozen ISOLATED guardrails. Therefore:

- eligible family winners = 0;
- promotion decision rows = 0;
- bootstrap comparison rows = 0.

The frozen lexicographic protocol therefore retains the incumbent reference. This
is not a post-hoc fallback and does not require relaxing any guardrail or margin.

The mandatory propagated check passed. Because no challenger survived ISOLATED
guardrails, the propagated surface is a `REFERENCE -> REFERENCE` self-check. It
confirms no propagated guardrail violation for the retained incumbent, but it is
not interpreted as an additional pairwise model comparison.

## Boundaries

This MAIN freeze:

- does not reopen CAL;
- does not open TEST;
- does not authorize the next component execution;
- does not evaluate G2;
- does not modify candidate models, seeds, margins, tolerances, CRN, bootstrap
  settings, or the count-observability remediation.
