# F3.3c — PRE-CAL Execution Harness Contract v1

## Purpose

F3.3c connects the already-frozen F3.3a selection core and F3.3b component adapters
to a common stochastic-evaluation evidence layer.

This phase **does not open CAL** and **does not select a candidate**.

## Execution identity

Every stochastic evidence row is identified by:

- component;
- artifact;
- evaluation mode;
- replicate id;
- evaluation person id;
- within-person event index.

The candidate-independent random seed is derived only from:

`master_seed | scenario_id | evaluation_person_id | component | draw_index`

Artifact/candidate/grid identity is deliberately absent from the seed.

## Replication

Exactly 32 stochastic replicates are required.

`replicate_id = 0..31`

## Event-index packing

F3.3c freezes:

`draw_index = (replicate_id << 32) | event_index`

`event_index=0` for day-level draws.

For event-level components the event index is the zero-based trip/transition slot in
the evaluated state.

This encoding is collision-free while `event_index < 2^32`.

## Evaluation person seed identity

F3.3c freezes:

`evaluation_person_id = "CAL|" + source_household_id + "|" + source_person_id`

The identity is provenance/seed material only and must never enter a behavioral feature matrix.

## Evidence

`F3_3C_STANDARD_EVIDENCE_V1` stores:

- frozen artifact identity;
- ISOLATED/PROPAGATED mode;
- replicate/event identity;
- household identity;
- candidate-independent seed;
- original metric weight;
- canonical observed JSON payload;
- canonical generated JSON payload.

## Bootstrap

For each candidate comparison:

1. candidate evidence must be exactly paired;
2. CRN seeds must be identical;
3. resample whole households;
4. retain every person/event/replicate belonging to the resampled household;
5. recompute the primary metric separately for each of 32 stochastic replicates;
6. arithmetic-mean the 32 metric values;
7. define improvement as `incumbent_metric - challenger_metric`;
8. repeat 1000 times;
9. use the frozen 95% percentile interval.

## Boundaries

- CAL: UNOPENED
- TEST: SEALED
- selection: NONE
- pre-commit fixtures: synthetic only
