# F3.4g-2e — Held-out TEST Protocol PREOPEN v1

## Purpose
Freeze the final held-out TEST methodology before any TEST **outcome content** is read.

The F1 household split exists as assignment metadata, not as a materialized `TEST/` directory. Therefore this phase freezes the split identity and does not require or create TEST CSVs.

## Frozen held-out split identity
- manifest: `artifacts/runs/R2_eligibility_split_v1/split_manifest_reproduced.csv`
- SHA-256: `5d0d4f2a41bc93b131de96d85192d8ff7002878e28e87515a0f88cedf1cebde8`
- version: `berlin_mid2017_household_split_v1`
- split unit: `HOUSEHOLD`
- split seed: `20260912`
- manifest households: `1770`
- full assignment counts: TRAIN `1238`, CALIBRATION `268`, TEST `264`
- strict R_min counts: TRAIN `1219`, CALIBRATION `263`, TEST `260`, total `1742`

The strict subset is derived from `split_stratum.startswith("STRICT_RMIN_DONOR|")`.
Reading this split-assignment manifest is metadata access and does not expose held-out behavioral outcomes.

## TEST materialization rule
TEST outcome files are deliberately **not** materialized during PREOPEN. Materialization is deferred to the future commit-bound authorized TEST runner. The runner must use the frozen F1 household assignments and may not redefine, reshuffle, or resample TEST membership.

## Evaluation object
The final frozen SELECTED pipeline is evaluated against the frozen ALL_REFERENCE comparator. No candidate selection is permitted. No parameter, threshold, artifact, feature, or pipeline design may be changed because of TEST results.

## Metrics
The TEST evaluation reuses the exact F3.4g-1 Joint metric matrix: 17 total metrics, 14 decision-driving metrics, 3 report-only metrics, no composite score, no new thresholds, and the same maximum-worsening semantics versus ALL_REFERENCE.

## Stochastic protocol
- 32 replicates
- master seed `20261003`
- CRN across SELECTED and ALL_REFERENCE
- identical seed schedule across both pipelines

## Formal G2
Before TEST execution: `G2 = NOT_EVALUATED`.

After a valid authorized TEST execution, G2 PASS iff execution integrity passes, hard invariants are zero, all 14 decision metrics pass, artifact manifests remain frozen, and there is no post-TEST design change. G2 FAIL iff execution integrity passes but any decision condition fails.

## Single-use held-out rule
The holdout is consumed as soon as any TEST **outcome content** is read. Reading the frozen split-assignment metadata does not consume it. After TEST outcome I/O, same-holdout rerun and same-holdout tuning are forbidden.

## PREOPEN boundary
```text
split manifest metadata rows read = 1770
TEST outcome content rows read = 0
TEST outcome hashes computed = false
TEST outcome row counts read = false
TEST materialized = false
TEST open authorized = false
holdout consumed = false
G2 = NOT_EVALUATED
```
