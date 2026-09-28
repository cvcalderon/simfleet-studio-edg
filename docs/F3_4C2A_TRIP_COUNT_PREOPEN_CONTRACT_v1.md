# F3.4c-2a — Trip Count real-CAL runner PRE-OPEN

This phase implements the Trip Count CAL runner and validates it without opening a
new Trip Count CAL row.

## Safety boundary

The real runner exists after this overlay, but it cannot authorize itself. Real CAL
execution requires a separate F3.4c-2b JSON authorization bound to the exact committed
F3.4c-2a implementation commit.

During F3.4c-2a:

- Trip Count CAL rows read = 0.
- TEST rows read = 0.
- Trip Count candidate selection = NONE.
- TEST remains sealed.
- G2 remains NOT_EVALUATED.

## ISOLATED

The real runner will join `trip_count.csv` to static person-day context and evaluate
all five frozen Trip Count artifacts with weighted discrete CRPS on K.

Generated-outcome guardrails are evaluated over the 460 Participation person-days:
empirical NoTrip contributes K=0; empirical TripDay receives a Trip Count draw.

Candidate selection and promotion use ISOLATED only.

## PROPAGATED

After a provisional ISOLATED winner exists, the runner evaluates the reference and
that provisional winner using generated Participation from the MAIN-frozen PA1.

PA1 draws are common across Trip Count candidates and Trip Count draw seeds use the
frozen `DG_TRIP_COUNT` namespace. The propagated surface is guardrail-only.

A propagated guardrail failure blocks MAIN freeze and does not silently fall back to
a different candidate.
