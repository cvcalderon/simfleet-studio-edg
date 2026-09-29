# F3.4e-2b A1 failure analysis and remediation v1

## Observed failure

The first commit-bound A1 execution reached authorized real-CAL I/O and failed before candidate scoring with:

`ValueError: Unexpected trip_position_class: __MISSING_CONTEXT__`

The failed `.partial` RunBundle is evidence and must be preserved.

## Root cause

This is an implementation-contract mismatch, not corrupted CAL data.

F3.2a freezes `__MISSING_CONTEXT__` as an explicit retained state whenever optional upstream context is unavailable. Time Schedule TRAIN fitting used this state and explicitly prohibited complete-case collapse. The frozen CAL snapshot contains 35 such `time_trips` rows across 6 person-days; in those rows `source_trip_count_analogue` is missing by construction.

A second audit found empirical prefix overlaps in 2 CAL target rows. F3.2f TRAIN validation accepts such target rows because target validity is row-local (departure/arrival/duration identity); the sequential temporal invariant is a hard guardrail on generated draws, not a filter for observed reference targets.

## Remediation semantics

1. Preserve all 1243 CAL Time Schedule target rows. No silent drop.
2. Accept `__MISSING_CONTEXT__` as a valid `trip_position_class` feature state when and only when source K is missing.
3. For isolated generated draws with missing source K, pass `trips_remaining_after_current=None`. This does not invent K; all other temporal constraints remain enforced.
4. Validate observed CAL target bounds and departure/arrival/day-offset/duration identity, but do not reject observed targets because an optional teacher-forced previous-arrival prefix overlaps.
5. Continue enforcing `TEMPORAL_INVARIANT_VIOLATIONS = 0` on generated ISOLATED and PROPAGATED draws.
6. Distance Prior remains unauthorized, TEST remains sealed, G2 remains NOT_EVALUATED.

This is a controlled runtime remediation. It does not change the candidate universe, model artifacts, M2-TIME-01 definition, CRN schedule, bootstrap, selection rules, or frozen upstream PA1/COUNT_REF/CHA2.
