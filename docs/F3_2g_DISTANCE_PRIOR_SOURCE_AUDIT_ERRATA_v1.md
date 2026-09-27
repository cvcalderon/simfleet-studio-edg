# F3.2g — source-audit errata v1

This errata corrects the earlier standalone `F3_2g_DISTANCE_PRIOR_FROZEN_IMPLEMENTATION_BRIEF_v1.md` after direct reinspection of the authoritative F3.1a/F3.1b/F3.1c/F3.2a source files.

## What remains source-frozen

The source files explicitly support:

- `DIST_REF`: weighted unconditional raw-`wegkm` ECDF;
- `DIST_A`: weighted conditional inverse-ECDF on raw `wegkm` with `DIST_BACKOFF_V1`;
- `DIST_B`: quantile gradient boosting on raw `wegkm`;
- DIST_B quantiles `.05,.10,.25,.50,.75,.90,.95`;
- DB1: depth 2, leaves 4, min leaf 30, L2 1;
- DB2: depth 3, leaves 8, min leaf 30, L2 1;
- DB3: depth 3, leaves 8, min leaf 60, L2 1;
- raw `wegkm` primary, `wegkm_imp` sensitivity only, `km_routing` forbidden;
- `DIST_FEATURES_V1` semantic subset;
- `DIST_BACKOFF_V1` hierarchy and raw `source_n < 30` LOW_N trigger;
- CAL objective/guardrails and TEST sealing.

## Corrections to the earlier brief

The earlier brief overstated four implementation details as already frozen by F3.1c. Direct source inspection shows they were not specified at that level:

1. the concrete column-level encoder for the semantic `DIST_FEATURES_V1` set;
2. the exact interpolation-knot convention behind `weighted linear inverse-ECDF`;
3. DIST_B `learning_rate` and `n_estimators`;
4. the full-u quantile reconstruction / monotonic-tail rule for DIST_B.

These points are therefore **not inherited F3.1c facts**. They are explicitly frozen in F3.2g as `FROZEN_PRE_CAL_IMPLEMENTATION_CLARIFICATIONS`, before any CAL inspection.

## Scientific impact

No candidate family, target evidence, weight policy, frozen quantile grid, backoff hierarchy, CAL metric, promotion threshold or information boundary is changed. The correction is about provenance of implementation detail, not redesign after observing CAL.
