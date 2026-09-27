# F3.3c — PRE-CAL Implementation Clarifications v1

State: `FROZEN_PRE_CAL_IMPLEMENTATION_CLARIFICATIONS`

These decisions are fixed before CAL inspection.

## CLAR-01 — evaluation person identity

`CAL_PIPE_HH_PERSON_V1`

`CAL|<source_household_id>|<source_person_id>`

Purpose: deterministic seed/provenance identity only.

## CLAR-02 — replicate/event draw-index packing

`REPLICATE_U32_EVENT_U32_V1`

`draw_index = (replicate_id << 32) | event_index`

This avoids arbitrary strides and prevents collisions across the 32 replicate streams.

## CLAR-03 — day/event semantics

- DG_PARTICIPATION: event_index = 0
- DG_TRIP_COUNT: event_index = 0
- DG_ACTIVITY_CHAIN: zero-based transition slot
- DG_TIME_SCHEDULE: zero-based trip slot
- DG_DISTANCE_PRIOR: zero-based trip slot

For downstream candidate comparisons in PROPAGATED mode, already-selected upstream state
defines the event slots, so all candidates inside the component comparison see the same slots.

## CLAR-04 — evidence serialization

Observed/generated payloads use canonical sorted compact JSON.

The payload is evidence, not a feature source.

## CLAR-05 — bootstrap recomputation

A household bootstrap replicate never bootstraps pre-aggregated candidate scores.
It applies household multiplicities to the underlying standardized evidence, recomputes
the component metric per stochastic replicate, then averages the 32 metrics.

## CLAR-06 — CAL opening

The PRE-CAL code contains an explicit access guard. F3.3c pre-commit execution is invalid
if CAL or TEST authorization is enabled.
