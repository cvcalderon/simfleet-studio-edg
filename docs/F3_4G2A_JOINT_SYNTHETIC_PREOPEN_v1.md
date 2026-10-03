# F3.4g-2a — Joint Synthetic PRE-OPEN v1

## Purpose

Validate the implementation path for the final selected-vs-all-reference Joint
CAL comparison **without reading CAL** and without opening TEST.

The synthetic smoke executes the real frozen adapters end-to-end for both
pipelines:

```text
SELECTED
PA1 -> COUNT_REF -> CHA2 -> TIME_B_TB2 -> DIST_REF

ALL-REFERENCE
PART_REF -> COUNT_REF -> CHAIN_REF -> TIME_REF -> DIST_REF
```

The same frozen runtime seed protocol is used for both pipelines.

## Synthetic cohort

Eight artificial person-days are generated from TRAIN-fitted encoder/category
support only. They are not empirical CAL rows and are not used for scientific
selection.

No observed same-day outcome, exact OD, route, `km_routing`, target purpose,
observed trip count, observed activity chain, observed time, or observed
distance is used as runtime input.

## What is tested

- exact artifact identities and hashes;
- 5 component slots per pipeline;
- 32 paired CRN replicates;
- actual Participation, Trip Count, Activity Chain, Time Schedule and Distance
  adapters;
- end-to-end propagation with no teacher forcing;
- chain continuity;
- temporal validity;
- positive finite generated distance;
- no future-information fields in static runtime context;
- RunBundle generation and checksums;
- synthetic metric smoke for purpose/time/distance.

Synthetic metrics are **non-decision evidence**. They cannot select an artifact,
evaluate the Joint gate, authorize CAL, open TEST, or close G2.

## Boundaries

```text
CAL files read = []
CAL rows read = 0
Joint real CAL = NOT_AUTHORIZED
Joint gate evaluated = false
TEST files read = []
TEST rows read = 0
G2 = NOT_EVALUATED
```
