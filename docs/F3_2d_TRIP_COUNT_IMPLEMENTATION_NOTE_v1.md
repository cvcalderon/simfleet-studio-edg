# F3.2d — DG_TRIP_COUNT implementation note v1

## Scope

This overlay implements **TRAIN-only fitting** for the already-frozen `DG_TRIP_COUNT` candidate slate. It does not open CAL for fitting/scoring/selection and does not consume TEST.

Frozen empirical universe: `REF_TRAIN_CORE_STRICT_COUNT_MOBILE`, materialized as `TRAIN/trip_count.csv`, `n=1791`, with `K>=1`, `K_MAX_TRAIN=50`, and fitting weight `P_GEW`.

## Candidate implementations

- `COUNT_REF`: weighted unconditional empirical PMF over the full integer support `K=1..50`; unobserved counts receive zero empirical mass.
- `COUNT_A/CA1..CA3`: NB2 regression on `Y=K-1`, log link, `Var(Y|X)=mu+alpha*mu^2`, joint TRAIN MLE of regression parameters and dispersion, with frozen L2 penalties `0`, `.1`, `1` on coefficients only. Runtime count PMFs are explicitly truncated and renormalized to `K=1..50`; no draw is post-hoc clipped.
- `COUNT_B/CB1`: weighted empirical conditional PMFs with literal `COUNT_BACKOFF_V1`. Cell support counts are raw TRAIN row counts; direct use requires `source_n>=30`; `P_GEW` controls probabilities only within cells. No smoothing and no rare-category pooling are introduced.

## Operational implementation details frozen before fitting

`COUNT_A` uses deterministic TRAIN-only reference-category one-hot encoding. The reference category is the first observed canonical lexical category per field. `__MISSING_CONTEXT__` and `__UNSEEN__` remain explicit categories. Reference coding is required so the unregularized `CA1` is identifiable in the presence of an intercept.

The weighted objective is the weighted-mean NB2 negative log-likelihood plus `0.5*lambda_l2*||beta||^2`. The intercept and dispersion are unpenalized. Dispersion is parameterized as `alpha=exp(log_alpha)` and estimated jointly from TRAIN. L-BFGS-B uses broad numerical guards (`coefficient/intercept [-20,20]`, `log_alpha [-12,8]`); an accepted fit is required not to terminate on a bound. Initial dispersion is the TRAIN weighted method-of-moments estimate with a `0.1` floor; this is an initialization only, not a fitted constraint.

`COUNT_B` preserves the frozen backoff hierarchy literally. Although `source_season` belongs to `COUNT_FEATURES_V1`, no season-conditioned empirical level is added because `COUNT_BACKOFF_V1` contains none.

## No-selection rule

TRAIN metrics are diagnostics only. Every artifact remains `FITTED_TRAIN_ONLY_NOT_SELECTED`; `cal_metrics=null`, calibration/selection are `NOT_EVALUATED`, and TEST remains sealed.
