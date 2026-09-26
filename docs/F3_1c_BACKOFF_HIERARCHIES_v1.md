# F3.1c — Frozen backoff hierarchies v1

All cell support counts are **raw strict-TRAIN source rows before weighting**. Direct conditional sampling requires `source_n >= 30`. `P_GEW`/`W_GEW` define probabilities only inside an eligible cell. CAL and TEST never create support.

## COUNT_BACKOFF_V1

1. age + sex + primary activity + household size + weekday
2. age + sex + primary activity + household size
3. age + sex + primary activity
4. age + primary activity
5. primary activity
6. age
7. global positive-count PMF

## CHAIN_BACKOFF_V1

1. last two activities + remaining trips + primary activity + weekday
2. last activity + remaining trips + primary activity + weekday
3. last activity + remaining trips + primary activity
4. last activity + remaining trips
5. last activity
6. remaining trips
7. global transition model

`START` is an explicit chain token. For generated trip count `K`, the generator emits exactly `K` transitions. The final activity is sampled; HOME is **not** forced.

## TIME_BACKOFF_V1

1. origin + destination activity + position class + primary activity + weekday
2. origin + destination activity + position class + primary activity
3. origin + destination activity + position class
4. destination activity + position class
5. position class
6. global timing kernel

A sampled schedule that violates frozen temporal invariants is rejected. Candidate `TIME_A` gets at most 100 attempts at the current support level, then moves one deterministic backoff level. No silent clock repair is permitted.

## DIST_BACKOFF_V1

1. origin + destination activity + departure period + primary activity + age
2. origin + destination activity + departure period + primary activity
3. origin + destination activity + departure period
4. origin + destination activity
5. destination activity
6. global raw-`wegkm` ECDF

Departure periods are deterministic from the **generated** departure clock: NIGHT 00:00–05:59, AM_PEAK 06:00–09:59, DAY 10:00–15:59, PM_PEAK 16:00–19:59, EVENING 20:00–23:59.

Every backoff event is persisted with requested key, selected level, raw source_n, candidate id and seed/draw identity.
