# F3.1a — D_GEN decomposition + information/feature contract freeze v1

## Status

`F3.1a = READY_FOR_REPOSITORY_FREEZE`

This subphase freezes the causal/runtime boundary before any model-family choice. It is PRE-G1 experimental design work: G1 remains open and formal G2 is not evaluated.

## Authoritative inputs

- `SimFleet_EDG_PartC_Checkpoint_after_R7_v1.md`
- `PRE_F3_REPRODUCTION_REPORT_v1.md`
- `F3_1_DGEN_MODEL_DESIGN_FREEZE_ENTRY_v1.md`
- frozen F0.3 NoFutureInformation / demand evidence contracts
- accepted R7 F2.2 metric universes and diagnostics

## 1. D_GEN causal decomposition

```text
M1 state + scenario-known context + frozen ModelArtifacts
                         |
                         v
                DG_PARTICIPATION
                  /           \
             NO_TRIP         TRIP_DAY
               |                |
       PersonDayPlan        DG_TRIP_COUNT (K>=1)
       trip_count=0              |
       zero TripIntent           v
                         DG_ACTIVITY_CHAIN
                         K transitions
                                |
                                v
                         DG_TIME_SCHEDULE
                                |
                                v
                         DG_DISTANCE_PRIOR
                                |
                                v
                      PersonDayPlan + K TripIntent
                                |
                   +------------+-------------+
                   |                          |
                  M3                         M5
        exact spatial realization       mode choice
```

The DAG is deliberately not monolithic. A downstream D_GEN component may consume outputs already generated upstream in the same plan. It may never consume realised donor outcomes or future, not-yet-generated states.

## 2. Components frozen in F3.1a

### DG_PARTICIPATION
Generates `TRIP_DAY` versus `NO_TRIP`. `NO_TRIP` is participation, never a mode. A generated `NO_TRIP` day terminates M2 generation with `trip_count=0` and no TripIntent rows.

### DG_TRIP_COUNT
Runs only for `TRIP_DAY`. Generates positive integer K. The full generated day-count distribution is reconstructed by combining the participation branch (K=0) with this conditional positive-count component.

### DG_ACTIVITY_CHAIN
Generates the functional activity/purpose transition sequence conditional on K and static/runtime context. It must generate exactly K transitions. Return-home behavior is a learned/generated sequence property, not an unconditional hard-coded rule.

### DG_TIME_SCHEDULE
Realises the generated chain temporally. It consumes the generated chain, not source donor times. Invalid generated chronology must be handled explicitly by the future sampling/constraint policy rather than silently repaired from source outcomes.

### DG_DISTANCE_PRIOR
Generates an M2 distance/path-length prior after chain/time generation. Primary empirical evidence is raw `wegkm` under `DIRECT_SOURCE_DISTANCE_VALID`; `wegkm_imp` is expanded/sensitivity evidence. `km_routing` is forbidden. The value is not an exact OD coordinate or Euclidean separation.

## 3. Runtime information boundary

Every candidate variable belongs to exactly one of:

- `ALLOWED_RUNTIME`
- `FIT_ONLY_EVIDENCE`
- `FORBIDDEN_FUTURE_INFORMATION`
- `IDENTIFIER_PROVENANCE_ONLY`

The complete registry is `F3_1a_INFORMATION_FEATURE_REGISTRY_v1.csv`.

A source outcome may be a fitting label without becoming a runtime predictor. Weights and quality flags may control fitting/eligibility without becoming behavioral features.

## 4. Calendar/context rule

Observed source weekday/holiday/season may support fitting, but D_GEN runtime uses the analogue deterministically derived from the scenario date. It never copies the donor survey date into the generated day. `survey_year` remains provenance and does not turn the hybrid reference into a single-year system.

## 5. Geography/resource rule

Generated home geography may be candidate context, subject to low-support/backoff policy. This does not authorize exact destination generation in M2. Exact spatial realization remains M3.

`Ownership != Access != Availability(t)`. Static ownership/access may be candidate M1 context; dynamic future availability is not silently treated as known daily-demand input.

## 6. Empirical target universes

Fitting/reference universes are task-specific and strict-TRAIN. D_MATCH remains diagnostic and is not promoted to ground truth. See `F3_1a_COMPONENT_TARGET_MAPPING_v1.csv`.

Key mapping:

- participation -> `REF_TRAIN_BINARY`, P_GEW;
- count -> strict count evidence, conditional positive-count component, P_GEW;
- chain/purpose/transitions -> full-functional/direct eligible evidence, W_GEW (with day-level P_GEW where appropriate);
- time -> `DIRECT_TEMPORAL_VALID`, W_GEW;
- distance -> `DIRECT_SOURCE_DISTANCE_VALID`, W_GEW; expanded imputed evidence remains sensitivity-only.

## 7. Output boundary

D_GEN outputs `PersonDayPlan` and `TripIntent` records sufficient for M3/M5. It does not emit:

- exact destination coordinate;
- route geometry;
- feasible alternatives;
- observed/chosen mode;
- execution outcome;
- `km_routing`.

`Trip != Stage`; stages remain separate/downstream and MiD Etappen remain diagnostic-only nonrepresentative evidence.

## 8. Low-support/bias guardrails

F3.1a carries forward:

- complete-diary selection bias;
- incomplete exact-replay coverage;
- finite diary diversity;
- low-support groups must be flagged (`FLAG_NOT_POOL`), not silently pooled;
- synthetic N does not increase empirical evidence N.

Concrete model-specific backoff thresholds are deferred to F3.1b because they depend on candidate model families, but the no-silent-pooling rule is frozen now.

## 9. Reproducibility rule

The future implementation must persist named seed namespaces by component, deterministic preprocessing order, candidate ordering wherever sampling depends on order, ModelArtifact/config hashes, and failure/retry history. The R6 RNG-provenance gap must not recur.

## 10. Explicit non-decisions

F3.1a intentionally does **not** choose logistic regression, trees/boosting, neural networks, empirical sampling, Markov models or any other concrete family. It also does not freeze CAL tuning thresholds. Those belong to F3.1b after this contract is committed.

## 11. Acceptance criteria for closing F3.1a

F3.1a can close when the repository verifies that:

1. the five-component DAG and order are machine-readable;
2. every registry entry has exactly one allowed information class;
3. no source IDs/weights are runtime behavioral features;
4. no M3/M5/execution fields are D_GEN runtime inputs/outputs;
5. TEST remains sealed;
6. component source universes and weighting roles are declared;
7. low-support and hybrid-reference caveats are retained;
8. model-family selection remains explicitly deferred to F3.1b;
9. boundary invariants pass automatically.

If these pass, the next authorized task is `F3.1b — candidate model-family decision + fitting/calibration protocol`.
