# F3.3a — CAL evaluation contract core v1

## Boundary

This overlay implements protocol primitives only. It **must not read CAL outcomes**. CAL remains unopened and TEST remains sealed.

## Frozen order

1. DG_PARTICIPATION
2. DG_TRIP_COUNT
3. DG_ACTIVITY_CHAIN
4. DG_TIME_SCHEDULE
5. DG_DISTANCE_PRIOR

For each component, retain the simpler incumbent unless a more complex preregistered family clears every frozen promotion condition.

## Required CAL views in the later adapter phase

- `ISOLATED`: empirical CAL upstream state may be used only to isolate the component under evaluation.
- `PROPAGATED`: rerun using already-selected upstream generators.

Teacher forcing is evaluation-only and is never a runtime feature.

## Replication and uncertainty

- 32 paired stochastic replicates per CAL person.
- Common random numbers; master seed 20260926; scenario `CAL_EVAL_V1`.
- 1000 paired household bootstrap replicates.
- 95% percentile CI for paired primary-metric improvement.
- Original P_GEW/W_GEW stay attached inside resampled households.

## Primary metrics

- Participation: weighted Bernoulli log-loss.
- Trip count: weighted discrete CRPS on K.
- Activity chain: weighted next-activity log-loss.
- Timing: `M2-TIME-01` TVD using the frozen hourly departure distribution.
- Distance: `M2-DIST-01` weighted 1-D Wasserstein distance in km on raw-distance evidence.

## Reused F2.2 guardrail definitions

- M2-PART-01: trip-day share.
- M2-COUNT-01: mean trips/person/day.
- M2-COUNT-02: trip-count distribution `0..11,12+`.
- M2-CHAIN-01: trips/mobile-day distribution.
- M2-PURP-01: canonical purpose distribution.
- M2-TIME-01: departure-hour distribution (hour = floor(clock_minute/60)).
- M2-RET-01: return-home share among functional mobile days.
- M2-TRANS-01: origin→destination activity-transition distribution.
- M2-DIST-01: raw observed trip-distance distribution; Wasserstein + mean/p50/p90/p95.
- M2-DIST-02: observed+source-imputed sensitivity, report-only.
- M2-COND-01/02: static subgroup participation/trip-count checks for age, sex, primary activity and household-size class. `source_n<30` is LOW_N/report-only.

## Joint gate before TEST

The later selected D_GEN pipeline must be compared on CAL with the all-reference pipeline. TEST opening requires zero structural/temporal/NoFutureInformation violations, no selected component dominated under the frozen rules, no material degradation beyond frozen guardrails, and frozen selected-artifact identities.
