# F3.2f — DG_TIME_SCHEDULE implementation note v1

## 1. Frozen inputs

F3.2f consumes only the frozen F3.2a TRAIN materialization:

- `person_day_context.csv`: 2200 rows
- `time_trips.csv`: 6103 rows
- unresolved optional transition context retained: 329 timing rows

## 2. TIME_FEATURES_V1

The runtime semantics are represented in TRAIN by source analogues:

- static core: age, sex, primary activity, household size;
- scenario-known calendar analogues: weekday, season;
- generated K analogue;
- generated chain analogue: origin activity, destination activity, trip position;
- generated time prefix analogue: previous departure clock and previous arrival absolute minute.

IDs, weights, targets, mode, routing and execution are never predictors.

## 3. TIME_A kernel clarification frozen before CAL

F3.1c froze bandwidths `0/15/30 min`, rejection count `100` and `TIME_BACKOFF_V1`, but did not name the kernel shape. F3.2f therefore freezes the missing implementation detail **before any CAL inspection**:

`DISCRETE_CIRCULAR_UNIFORM_INTEGER_V1`

For an empirical support tuple `(departure, duration)`, draw integer jitter uniformly and inclusively from `[-bandwidth,+bandwidth]`, wrap departure modulo 1440, keep the empirical joint duration, reconstruct arrival from generated departure + duration, and reject any invalid chronology. After 100 failed attempts at the current support level, move deterministically to the next backoff level. There is no silent clock repair.

This clarification does not inspect CAL and does not change the F3.1c grid.

## 4. TIME_B

Each grid fits two independent weighted quantile targets:

- departure clock minute;
- planned duration minute.

Seven LightGBM quantile regressors are fitted per target. Runtime quantiles are monotonised with the frozen cumulative-max rule before interpolation. Generated values must still pass temporal invariants; model output is never silently clipped into validity.

## 5. Temporal invariants

- departure clock in `[0,1439]`;
- duration `>=1`;
- arrival is reconstructed from departure + duration;
- arrival day offset must be 0 or 1;
- if a generated prefix exists, current departure cannot precede previous generated arrival;
- a non-final trip cannot end after the represented generation day because later departures have no departure-day-offset field;
- failures trigger rejection/resampling, never donor/source repair.
