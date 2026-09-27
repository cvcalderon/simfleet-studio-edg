# F3.3b — PRE-CAL Implementation Clarifications v1

These clarifications are frozen before any CAL row or metric is inspected.

## A. Adapter schema

`FIT_ANALOGUE_SCHEMA_V1` is the adapter boundary. ISOLATED empirical upstream values and PROPAGATED generated upstream values are projected to the exact same model-facing fields. Missing context keeps the already-frozen missing/NaN semantics; no complete-case filtering is introduced.

## B. Component namespace

For CRN seed derivation, `component_namespace` is exactly the canonical component id (`DG_PARTICIPATION`, `DG_TRIP_COUNT`, etc.). Candidate/grid ids are deliberately excluded so candidate comparisons share the same event seed.

## C. TIME_REF runtime rejection

`TIME_REF_RUNTIME_REJECTION_V1`:

- sample the frozen global empirical `(departure,duration)` support;
- validate chronology/arrival/future-trip invariants;
- reject invalid draws without clock repair;
- maximum 100 attempts; failure is explicit.

F3.2f froze rejection semantics but not the finite cap. The value 100 is aligned with the already-frozen TIME_A cap.

## D. TIME_B runtime sampling

`TIME_B_RUNTIME_SAMPLING_V1`:

1. predict q=.05,.10,.25,.50,.75,.90,.95 separately for departure and duration;
2. clamp predicted knots to frozen global TRAIN supports: departure `[0,1439]`, duration `[1,480]`;
3. cumulative-max repair;
4. add q=0/q=1 global endpoints;
5. linearly interpolate in quantile probability;
6. use independent departure and duration uniforms from the same event-seeded RNG stream;
7. round to integer minutes with deterministic `ROUND_HALF_UP`;
8. reject invalid pairs and resample, max 100 attempts;
9. never silently repair chronology.

Independent uniforms are used because the fitted family contains separate marginal quantile models and no learned dependence/copula. Reusing one uniform would introduce an unfitted comonotonic dependence.

## E. No CAL selection consequence yet

These rules make frozen artifacts executable. They do not inspect candidate performance and do not authorize CAL access by themselves.
