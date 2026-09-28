# F3.4b-2a — Participation real-CAL runner + PRE-OPEN gate v1

**Required parent:** `1c31cd3528b69bf24fb4434f7bde60188a8f8735`
**Entry state:** F3.4a SUPERADO · F3.4b-1 SUPERADO · CAL unread · TEST sealed.
**Purpose:** commit and validate the exact code that will later perform the first real CAL read, without reading CAL in this phase.

## Irreversible-boundary rule

F3.4b-2a is still PRE-OPEN. The real runner is implemented here, but it cannot open CAL without a separate external F3.4b-2b authorization document bound to the exact committed implementation hash.

```text
F3.4b-2a code + tests + PRE-OPEN verifier
                 ↓ commit exact bytes
F3.4b-2b external authorization bound to that commit
                 ↓
first real CAL read: DG_PARTICIPATION only
```

The implementation must never self-authorize.

## CAL inputs frozen

Only two files may be opened by the later authorized execution:

- `CALIBRATION/person_day_context.csv`: 469 rows, SHA-256 `83a826357b28b1be949f79e23d13cea07c00ad91390daa8f2eeaa17bea3f9d4a`;
- `CALIBRATION/participation.csv`: 460 rows, SHA-256 `6c9e9639f9e305232512a324a7a8c3ce6814355f9c538c08f575be0364304117`.

The physical-row read count of an official run is therefore 929 and the joined evaluation universe is exactly 460 person-days.

`TEST/` remains forbidden.

## Evaluation

Exactly 8 frozen TRAIN-fit Participation artifacts enter CAL. Primary selection uses direct weighted Bernoulli log-loss. M2-PART-01 and M2-COND-01 use 32 paired common-random-number realizations. Supported conditional cells require source `n >= 30`; LOW_N cells are report-only.

Sequential selection is exactly REF → best eligible A → best eligible B. Promotion requires hard/guardrail pass, point improvement >= 0.005 and 95% paired household-bootstrap lower CI > 0.

## PART_B calibration

Weighted sigmoid calibration is considered only if an uncalibrated PART_B grid is the selected base candidate. The retain/reject decision uses deterministic 5-fold household cross-fit. The log-loss gain is computed from cross-fit probabilities; the share-error guard uses M2-PART-01 exactly as an outcome metric: mean absolute trip-day-share error across the same 32 CRN realizations, with worsening capped at 0.005. If retained, the sigmoid is fitted on all CAL and stored as a derived proposed artifact. It cannot rescue an unselected PART_B grid.

## Output semantics

The real run may produce a **proposed** selected Participation artifact, but it is not downstream-authorized until MAIN reviews and freezes it.

```text
candidate_selection_state = PROPOSED_BY_FROZEN_RULES_AWAITING_MAIN_FREEZE
next_component_authorized = false
TEST = SEALED
formal G2 = NOT_EVALUATED
```
