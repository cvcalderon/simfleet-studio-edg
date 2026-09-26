# MAIN UPDATE — F3.2f DG_TIME_SCHEDULE prep

Status: PRECOMMIT PREP.

Frozen TRAIN anchor:

- `time_trips = 6103`
- expected models = `7`
- `TIME_REF x1`
- `TIME_A TA1/TA2/TA3 x3`
- `TIME_B TB1/TB2/TB3 x3`

Pre-CAL implementation clarification: `TIME_A` uses a discrete circular uniform integer departure jitter for the already-frozen `0/15/30 min` bandwidths. This decision is frozen before CAL inspection.

CAL remains unopened; TEST remains sealed; no selection occurs in F3.2f.
