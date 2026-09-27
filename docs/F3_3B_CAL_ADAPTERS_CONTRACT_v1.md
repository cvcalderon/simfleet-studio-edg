# F3.3b — Component CAL Adapters Contract v1

## Scope

F3.3b makes the 31 frozen TRAIN artifacts executable through a common evaluation adapter layer. It does **not** read CAL, compute CAL metrics, select a candidate, or open TEST.

The adapter boundary is the frozen fitting-analogue schema. Two upstream-state sources are supported:

- `ISOLATED`: empirical CAL upstream state, evaluation-only teacher forcing.
- `PROPAGATED`: generated state from already-selected upstream components.

No runtime code may substitute empirical upstream state in `PROPAGATED` mode.

## Components

- DG_PARTICIPATION: probability + Bernoulli draw.
- DG_TRIP_COUNT: positive-K PMF + count draw.
- DG_ACTIVITY_CHAIN: initial-activity PMF and next-activity PMF/draw.
- DG_TIME_SCHEDULE: valid planned departure/duration draw under temporal invariants.
- DG_DISTANCE_PRIOR: M2 path-length-prior draw.

## CRN boundary

Adapters accept a candidate-independent event seed derived from the F3.3a rule. The exact component id is the `component_namespace`. The future generation harness owns allocation of `draw_index`; F3.3b does not invent a replicate/event numbering scheme.

## PART_B

F3.3b exposes the raw frozen PART_B probability. The optional 5-fold weighted-sigmoid CAL calibration remains a later CAL evaluation step and is not fitted here.

## Data I/O boundary

F3.3b may read:

- frozen candidate registry;
- frozen TRAIN model artifacts/manifests;
- frozen encoder/support manifests.

F3.3b must not read:

- `CALIBRATION/*` rows;
- TEST rows;
- CAL metric output;
- selection decisions.
