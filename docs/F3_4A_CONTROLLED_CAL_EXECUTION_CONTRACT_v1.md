# F3.4a — Controlled CAL Execution Contract v1

**Required parent:** `3a6b0eb3e3ef4ab9311383a418c88d9e9ef20ada`
**State at entry:** F3.3d SUPERADO · CAL rows read = 0 · TEST SEALED · candidate selection = NONE.
**Purpose:** freeze the execution semantics of controlled CAL before implementing the CAL runner or reading CAL rows.

## 1. Scope

F3.4a does **not** read CAL. It freezes how CAL will be consumed later.

The CAL sequence is deliberately component-wise:

```text
DG_PARTICIPATION
      ↓ MAIN review + selected artifact freeze
DG_TRIP_COUNT
      ↓ MAIN review + selected artifact freeze
DG_ACTIVITY_CHAIN
      ↓ MAIN review + selected artifact freeze
DG_TIME_SCHEDULE
      ↓ MAIN review + selected artifact freeze
DG_DISTANCE_PRIOR
      ↓ MAIN review + selected artifact freeze
JOINT selected-vs-all-reference CAL gate
```

No command is allowed to select all five components unattended.

## 2. Candidate universe

The authoritative registry is `docs/F3_3_CANDIDATE_ARTIFACT_REGISTRY_v1.csv`, SHA-256
`14280b82fab60248e955fe6e5fc1ef45e487440021f0b1d424daca935c91cd9b`.

Exactly 31 TRAIN-fit artifacts are eligible:

| Component | Artifacts |
|---|---:|
| DG_PARTICIPATION | 8 |
| DG_TRIP_COUNT | 5 |
| DG_ACTIVITY_CHAIN | 6 |
| DG_TIME_SCHEDULE | 7 |
| DG_DISTANCE_PRIOR | 5 |

Every artifact must enter CAL with `train_state=FITTED_TRAIN_ONLY_NOT_SELECTED`.

## 3. CAL inputs

Only the physically isolated `CALIBRATION/` tables under
`artifacts/model_data/F3_2a_training_data_v1/` may be opened by the future runner.

Expected rows are frozen in `F3_4A_CAL_INPUT_MANIFEST_v1.csv`. F3.4a/verifier may test path existence only; it must not parse those files.

`TEST/` remains forbidden.

## 4. Frozen stochastic protocol

- scenario: `CAL_EVAL_V1`;
- master seed: `20260926`;
- 32 paired stochastic replicates;
- common random numbers;
- `evaluation_person_id = CAL|<source_household_id>|<source_person_id>`;
- `draw_index=(replicate_id << 32) | event_index`;
- 1000 paired household-bootstrap replicates;
- 95% percentile CI;
- original survey weights retained within resampled households.

## 5. Selection mechanics

No composite score.

Complexity order:

`REFERENCE_BASELINE < CORE_CANDIDATE_A < CORE_CHALLENGER_B`.

Inside A/B families with multiple grids:

1. reject HARD failures;
2. reject grids failing guardrails against the current lower-complexity incumbent;
3. choose the lowest primary metric;
4. exact tie -> lexical `grid_id`.

Then promote sequentially REF→best-A and current-incumbent→best-B only when all frozen conditions pass: practical margin, strictly-positive lower bootstrap CI, hard invariants and guardrails.

## 6. ISOLATED / PROPAGATED

Participation has no upstream D_GEN component and is evaluated once under the canonical `ISOLATED` evidence label.

Every downstream component requires:

- `ISOLATED`: empirical CAL upstream state for component isolation only;
- `PROPAGATED`: already-selected upstream D_GEN components generate state.

Teacher forcing remains evaluation-only.

## 7. Point-estimate clarification frozen before CAL

Deterministic proper scores that can be computed directly from predictive probabilities/PMFs are evaluated directly.

Metrics depending on generated realizations are computed independently for each of the 32 paired replicates and then arithmetically averaged.

For Participation specifically:

- primary weighted Bernoulli log-loss = direct probability score;
- M2-PART-01 / M2-COND-01 generation guardrails = mean of the 32 stochastic realization metrics.

This operationalizes the already-frozen F3.3a clarification without changing the scientific metric definitions.

## 8. PART_B calibration

`NONE` and `WEIGHTED_SIGMOID` remain the only options. Five deterministic household-level cross-fit folds are used.

The calibration decision is post family/grid selection. Therefore calibration cannot be used to rescue a PART_B family/grid that was not selected under the frozen family/grid protocol.

If retained, the authorized sigmoid is fit on all CAL only after the component family/grid is selected and is frozen as part of the selected participation artifact.

## 9. First controlled run

The first later CAL run is **DG_PARTICIPATION only**:

- 8 registered artifacts;
- CAL inputs: `person_day_context.csv` + `participation.csv`;
- primary: weighted Bernoulli log-loss;
- guardrails: M2-PART-01 and M2-COND-01;
- optional PART_B calibration only under the rule above;
- no downstream component execution in the same run.

The run stops and returns a RunBundle to MAIN.

## 10. Boundary after F3.4a

A successful F3.4a contract freeze authorizes only implementation of the F3.4b Participation CAL runner with synthetic/dry-run tests.

It does **not** itself read CAL.

```text
CAL rows read       = 0
candidate selection = NONE
TEST                = SEALED
formal G2           = NOT_EVALUATED
```
