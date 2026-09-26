# F3.2e — DG_ACTIVITY_CHAIN implementation note v1

## Scope

This overlay implements **TRAIN-only fitting** for the frozen `DG_ACTIVITY_CHAIN` slate. It does not read CAL for fitting/scoring/selection and does not consume TEST.

Primary transition fit weight is `W_GEW`. `P_GEW` is retained only for day-level sequence context/diagnostics such as the empirical initial-activity model; it is not a transition predictor.

## Candidate implementations

### CHAIN_REF

Weighted first-order empirical next-activity matrix conditioned on `prefix_last_activity`. A weighted global target PMF is serialized only as an unseen-state fallback. Return-home is not forced.

### CHAIN_A

Terminal-aware variable-order Markov/n-gram model with the literal `CHAIN_BACKOFF_V1` hierarchy:

1. last two activities + remaining trips + primary activity + weekday;
2. last activity + remaining trips + primary activity + weekday;
3. last activity + remaining trips + primary activity;
4. last activity + remaining trips;
5. last activity;
6. remaining trips;
7. global transition model.

Raw `source_n>=30` is required for direct non-global support. `W_GEW` defines category mass inside each cell. `CHA1` and `CHA2` differ only in Dirichlet alpha (`0.1`, `1.0`).

### CHAIN_B

Regularized multinomial logistic next-activity model. Semantic features are exactly `CHAIN_FEATURES_V1`:

- age;
- sex;
- primary activity;
- household size;
- weekday;
- generated trip count analogue;
- generated chain prefix;
- deterministic `remaining_trips` derived from K/current transition index.

No season, resource, purpose, weight, identifier, mode, route or execution field is added to the core-v1 feature matrix.

Categorical predictors use deterministic TRAIN-only reference one-hot coding. Numeric K/remaining-trip fields use TRAIN z-score scaling. The target support is the canonical lexical TRAIN-observed destination-activity support.

## Structural validation

The fitter validates before training that every `chain_days` record has exactly its declared K transition rows, indices are contiguous, `remaining_trips=K-index`, order-2 prefixes are internally consistent, and the last transition destination equals the day-level final destination.

The materialized TRAIN evidence currently starts every full-functional chain at HOME. This is recorded as empirical support, not introduced as a new universal theoretical rule. Final HOME is never forced.

## No-selection rule

TRAIN next-activity log loss and report-only diagnostics are not promotion decisions. CAL remains unopened in F3.2e and TEST remains sealed.
