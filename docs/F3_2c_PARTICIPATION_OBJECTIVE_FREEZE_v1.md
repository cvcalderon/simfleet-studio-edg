# F3.2c — DG_PARTICIPATION implementation objective freeze v1

This artifact fixes implementation-level details **before official TRAIN fitting**. It does not modify the F3.1c candidate families, features, grids, CAL promotion protocol, or TEST seal.

## PART_REF
`p = sum(P_GEW * target_trip_day) / sum(P_GEW)` on `REF_TRAIN_BINARY` only.

## PART_A
For each frozen `lambda_l2 ∈ {0.1, 1.0, 10.0}`, minimize

`weighted_mean_Bernoulli_NLL + 0.5 * lambda_l2 * ||beta||²`

with an unpenalized intercept. The weighted NLL is normalized by `sum(P_GEW)` so rescaling all survey weights by a common constant cannot change the optimizer. Optimization is deterministic SciPy L-BFGS-B with zero initialization, `maxiter=2000`, `ftol=1e-12`, `gtol=1e-8`.

## PART_B
Use LightGBM binary objective, `learning_rate=.05`, `n_estimators=200`, frozen PB1–PB4 structure/L2 values, full feature/bagging fractions, deterministic mode, `force_col_wise=true`, and `n_jobs=1`. `P_GEW` is sample weight only.

## Shared feature representation
PART_A and PART_B consume the exact same 15 semantic fields from `PART_FEATURES_V1`, encoded by one deterministic full one-hot matrix learned from TRAIN only. IDs, target, and weights are not in X. Unknown future categories route to `__UNSEEN__`; missing context routes to `__MISSING_CONTEXT__`.

## Phase boundary
F3.2c TRAIN fitting does not read CALIBRATION, does not calculate CAL metrics, does not fit a calibrator, does not promote a candidate, and does not access TEST. All fitted candidates remain `FITTED_TRAIN_ONLY_NOT_SELECTED`.
