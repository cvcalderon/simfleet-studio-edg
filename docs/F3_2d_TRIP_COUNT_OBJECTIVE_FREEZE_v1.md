# F3.2d — Trip-count implementation objective freeze v1

This document freezes implementation-level choices **before** the official TRAIN fit. It does not alter F3.1c candidate families, feature semantics, grids, promotion margins, or TEST policy.

## Frozen grid

- `COUNT_A/CA1`: NB2 on `K-1`, `lambda_l2=0`, dispersion `TRAIN_MLE`.
- `COUNT_A/CA2`: NB2 on `K-1`, `lambda_l2=.1`, dispersion `TRAIN_MLE`.
- `COUNT_A/CA3`: NB2 on `K-1`, `lambda_l2=1`, dispersion `TRAIN_MLE`.
- `COUNT_B/CB1`: `COUNT_BACKOFF_V1`, no free smoothing parameter.

## COUNT_A numerical objective

For TRAIN rows `i` with `Y_i=K_i-1` and weight `w_i=P_GEW_i`, fit

`sum_i w_i * (-log NB2(Y_i | mu_i, alpha)) / sum_i w_i + 0.5*lambda*||beta||^2`

with `log(mu_i)=intercept + X_i beta` and `Var(Y_i|X_i)=mu_i+alpha*mu_i^2`.

`alpha` is estimated jointly on TRAIN. Intercept and dispersion are unpenalized. The generated distribution is not clipped: NB2 mass is renormalized over `Y=0..49`, equivalent to `K=1..50`.

## COUNT_B support

`COUNT_BACKOFF_V1` is copied literally from F3.1c. `source_n<30` means `LOW_N`; such a cell is retained for audit but is not directly eligible. Runtime resolution backs off one frozen level at a time until an eligible cell is found. Global positive-count PMF is the terminal support.

All empirical support uses canonical lexical count keys `K:000001` ... `K:000050` for deterministic cumulative sampling.
