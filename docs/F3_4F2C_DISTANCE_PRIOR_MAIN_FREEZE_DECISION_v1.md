# F3.4f-2c — Distance Prior MAIN Freeze Decision v1

## Decision

`DIST_REF_REFERENCE = MAIN_FROZEN` for `DG_DISTANCE_PRIOR`.

This formalizes the artifact proposed by the frozen F3.4f-2b CAL rules. No
candidate, feature, threshold, metric, hyperparameter, upstream selection, or
TEST information is introduced after CAL inspection.

## Authoritative A1 evidence

The controlled A1 execution opened exactly the three authorized Distance CAL
inputs: 469 person-day context rows, 1,147 raw-distance rows, and 1,257
sensitivity rows, for 2,873 physical CAL rows. The fixed propagated source
cohort remained 350 person-days. Five frozen TRAIN artifacts entered the
evaluation and 32 paired CRN replicates were used.

The CAL execution was performed once at implementation commit
`1530cac0b4d634eb064bc46d5fb7ee429518d208`. The later verifier-only remediation
at `48dddece478e30a5e592f4eda681e0b972df02db` did not rerun CAL. The preserved
RunBundle and checksum/provenance verification passed.

## ISOLATED primary metric

Reported M2-DIST-01 values (mean-32 weighted 1D Wasserstein distance in km;
lower is better):

| Artifact | M2-DIST-01 | Hard pass |
|---|---:|---|
| DIST_REF_REFERENCE | **3.013478** | yes |
| DIST_A_DA1 | 2.590818 | yes |
| DIST_B_DB1 | 15.871673 | yes |
| DIST_B_DB2 | 16.015257 | yes |
| DIST_B_DB3 | 16.315302 | yes |

`DIST_A_DA1` has a point improvement of approximately **0.422660 km** versus
the reference, exceeding the preregistered practical margin of 0.25 km. That
fact alone is not sufficient for promotion because challenger eligibility also
requires all thresholded quantile guardrails to pass.

## Quantile guardrails

The frozen rule compares challenger minus incumbent mean-32 absolute weighted
quantile error and requires each of P50/P90/P95 to worsen by no more than
0.50 km.

For `DIST_A_DA1` versus `DIST_REF_REFERENCE`:

- P50 worsening: -0.049508 km — pass;
- P90 worsening: +0.158035 km — pass;
- P95 worsening: **+1.852904 km — fail**.

Therefore `DIST_A_DA1` is not guardrail-eligible and is not a within-family
candidate for promotion.

All three DIST_B candidates also fail the thresholded guardrails, with P90/P95
worsenings far above 0.50 km.

## Bootstrap / promotion interpretation

The preregistered paired household bootstrap has 1,000 replicates, but it is
only reached for a hard-pass, guardrail-pass challenger selected within a
family. No Distance challenger satisfied that prerequisite.

Accordingly:

- `bootstrap_intervals.csv` is intentionally empty;
- `promotion_decisions.csv` is intentionally empty;
- no post-hoc bootstrap criterion is introduced;
- the incumbent remains `DIST_REF_REFERENCE` by the frozen lexicographic rule.

This is not a missing calculation: promotion was never reached because the
guardrail eligibility stage rejected every challenger.

## Report-only evidence

MEAN remains `REPORT_ONLY_UNTHRESHOLDED`. M2-DIST-02 on `wegkm_imp` remains
`REPORT_ONLY`. Neither can override the thresholded guardrail failure.

Reported M2-DIST-02 values:

| Artifact | M2-DIST-02 |
|---|---:|
| DIST_REF_REFERENCE | 2.785627 |
| DIST_A_DA1 | 2.500009 |
| DIST_B_DB1 | 16.241821 |
| DIST_B_DB2 | 16.452159 |
| DIST_B_DB3 | 16.741100 |

## PROPAGATED hard runtime guardrail

Under the frozen upstream state:

`PA1 + COUNT_REF + CHA2 + TIME_B_TB2`

the incumbent reference generated **36,449** distance rows with:

- runtime invariant violations: **0**;
- hard pass: **true**.

PROPAGATED remains a hard-runtime-admissibility-only check and does not redefine
the primary metric.

## Frozen artifact identity

- artifact: `DIST_REF_REFERENCE`;
- candidate: `DIST_REF`;
- grid: `REFERENCE`;
- role: `REFERENCE_BASELINE`;
- TRAIN implementation commit: `a128dd29ca4d3d99545039c458ddac68159b592f`;
- official TRAIN run: `F3_2g_distance_prior_fit_v1`;
- model: `models/DIST_REF/model.json`;
- model SHA-256: `21554c37d44aad7144c8daac1ddfd9e9a63402d59e105f9e790e83c1ea6e4cab`;
- artifact manifest: `models/DIST_REF/artifact_manifest.json`;
- manifest SHA-256: `4a30ae1f586418c31a55028e2902d28c43e234a1fddaadccba9103c1a09bd409`.

## Semantic boundary retained

Generated distance remains:

`M2_PATH_LENGTH_PRIOR_FOR_M3_NOT_EXACT_OD_OR_ROUTED_DISTANCE`.

`wegkm` is the primary empirical target, `wegkm_imp` is report-only sensitivity,
and `km_routing` is not consumed.

## Boundaries after commit

- `DG_DISTANCE_PRIOR / DIST_REF_REFERENCE`: MAIN_FROZEN;
- Distance Prior D_GEN runtime use: AUTHORIZED;
- all five D_GEN component selections: MAIN_FROZEN;
- Joint selected-vs-all-reference CAL gate: NOT_AUTHORIZED;
- TEST: SEALED;
- formal G2: NOT_EVALUATED.

No Joint CAL or TEST access is authorized by this overlay.
