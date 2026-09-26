# F3.2e — Activity-chain implementation objective freeze v1

This document freezes implementation-level choices **before** the official TRAIN fit. It does not alter F3.1a/F3.1b/F3.1c candidate families, feature semantics, CAL promotion rules, or TEST policy.

## Authoritative TRAIN universe

F3.2a is the implementation-level materialization authority:

- `TRAIN/chain_days.csv`: **1422** full-functional mobile person-days;
- `TRAIN/chain_transitions.csv`: **4872** eligible transitions;
- `TRAIN/person_day_context.csv`: **2200** strict-TRAIN person-day context rows.

The earlier F3.1b descriptive source count of 5812 transitions is not used as the fitting row-count contract. F3.2a explicitly froze the 4872-row intersection used by implementation.

## Frozen candidate grid

- `CHAIN_REF`: weighted first-order transition matrix conditioned on previous activity.
- `CHAIN_A/CHA1`: terminal-aware order<=2 Markov/n-gram, `CHAIN_BACKOFF_V1`, Dirichlet `alpha=0.1`.
- `CHAIN_A/CHA2`: same with Dirichlet `alpha=1.0`.
- `CHAIN_B/CHB1`: regularized multinomial next-activity model, `lambda_l2=0.1`.
- `CHAIN_B/CHB2`: same with `lambda_l2=1.0`.
- `CHAIN_B/CHB3`: same with `lambda_l2=10.0`.

Total expected serialized models: **6**.

## Sequence semantics

For generated positive trip count `K`, the chain generator emits exactly `K` transitions and exactly `K+1` activity states. `__START__` is an explicit prefix token. The final activity is sampled from the fitted sequence model; `HOME` is **not** universally forced.

Source prefixes are fitting evidence analogues. Runtime generation must consume generated prefix state. Source future activities, source return-home outcomes and same-transition purpose are not runtime predictors.

## CHAIN_A support

`CHAIN_BACKOFF_V1` is copied literally from F3.1c. Cell support counts are raw strict-TRAIN transition rows before weighting. A non-global cell is directly eligible only when `source_n>=30`. `W_GEW` determines target probabilities within a cell. Dirichlet smoothing is applied over the full TRAIN-observed destination-activity support.

## CHAIN_B objective

`CHAIN_B` uses deterministic TRAIN-only encoding. Categorical fields use reference-category one-hot encoding with explicit `__MISSING_CONTEXT__` and `__UNSEEN__` tokens. `generated_trip_count` and derived `remaining_trips` analogues are numeric and standardized using TRAIN mean/scale.

For transition rows `i`, target class `y_i` and weight `w_i=W_GEW_i`, the objective is weighted mean multinomial cross-entropy plus:

`0.5 * lambda_l2 * ||beta||^2`

Intercepts are unpenalized. Coefficients are fitted by deterministic SciPy L-BFGS-B. The canonical first target activity is the reference class.

## TRAIN-only rule

F3.2e emits TRAIN diagnostics only. Every serialized artifact remains `FITTED_TRAIN_ONLY_NOT_SELECTED`; `cal_metrics=null`; candidate selection remains `NOT_EVALUATED`; TEST remains sealed.
