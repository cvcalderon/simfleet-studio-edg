# MAIN UPDATE — F3.2g DG_DISTANCE_PRIOR prep

Status: PRECOMMIT PREP.

Frozen TRAIN anchors:
- raw distance rows: 5,617
- expanded sensitivity rows: 6,145 (report-only)
- expected models: 5
- DIST_REF x1
- DIST_A DA1 x1
- DIST_B DB1/DB2/DB3 x3

Pre-CAL implementation clarifications are explicitly frozen for the concrete DIST_FEATURES_V1 encoder, weighted inverse-ECDF knot convention, omitted DIST_B learning-rate/estimator-count values, and full-u quantile reconstruction.

CAL remains unopened; TEST remains sealed; no selection occurs in F3.2g.
