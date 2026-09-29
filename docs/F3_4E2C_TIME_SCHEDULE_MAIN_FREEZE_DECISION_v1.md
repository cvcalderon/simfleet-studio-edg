# F3.4e-2c — Time Schedule MAIN Freeze Decision v1

## Decision

`TIME_B_TB2 = MAIN_FROZEN` for `DG_TIME_SCHEDULE`.

This formalizes the artifact proposed by the frozen F3.4e-2b CAL rules. No
candidate, feature, threshold, metric, hyperparameter, upstream selection, or
TEST information is introduced after CAL inspection.

## Authoritative A6 evidence

A6 opened exactly the authorized Time Schedule CAL inputs: 469 person-day
context rows plus 1243 time-trip rows, for 1712 physical CAL rows. The fixed
propagated source cohort remained 378 person-days. Seven frozen TRAIN artifacts
entered the evaluation; 32 paired CRN replicates and the preregistered 1000
household bootstrap were used.

The A6 RunBundle and its checksum audit passed, and the official RunBundle
verifier returned PASS with zero failed checks.

## ISOLATED selection

Reported M2-TIME-01 values (mean-32 departure-hour TVD; lower is better):

| Artifact | M2-TIME-01 | Hard pass |
|---|---:|---|
| TIME_REF_REFERENCE | 0.252671 | yes |
| TIME_A_TA1 | n/a | no |
| TIME_A_TA2 | n/a | no |
| TIME_A_TA3 | n/a | no |
| TIME_B_TB1 | 0.115787 | yes |
| TIME_B_TB2 | **0.112080** | yes |
| TIME_B_TB3 | 0.112718 | yes |

`TIME_B_TB2` is therefore the frozen-rule within-family B selection.

## Promotion REF -> TB2

- reported point improvement: 0.140591;
- practical margin: 0.005;
- paired household bootstrap: 1000 replicates;
- reported CI95: [0.084075, 0.163467];
- lower CI bound > 0;
- promotion: PASS.

The immutable A6 RunBundle remains the source of exact machine-precision values;
the decimal values above are the reported audit values from the final review.

## Temporal hard guardrails

ISOLATED:

- `TIME_REF_REFERENCE`: 0 violations;
- `TIME_B_TB2`: 0 violations.

PROPAGATED under the frozen `PA1 + COUNT_REF + CHA2` upstream state:

- `TIME_REF_REFERENCE`: 0 violations across 39,449 generated time rows;
- `TIME_B_TB2`: 0 violations across 39,449 generated time rows;
- frozen conjunctive reference-and-incumbent gate: PASS.

The propagated sampling remediation preserves candidate identity and fitted
artifacts. `TIME_B` uses full-chain minimum-slack conditioning and `TIME_REF`
uses complete-path conditioning over its already-frozen empirical support.

## Frozen artifact identity

- artifact: `TIME_B_TB2`;
- candidate: `TIME_B`;
- grid: `TB2`;
- TRAIN implementation commit: `799d5c6085c7c29ba7e83e02d37b37aac22ee296`;
- official TRAIN run: `F3_2f_time_schedule_fit_v1`;
- model: `models/TIME_B/TB2/model.json`;
- model SHA-256: `74aa012647291854c4fa087f1dd798e9d909e3c681046f1447307a23a6d5f900`;
- artifact manifest: `models/TIME_B/TB2/artifact_manifest.json`;
- manifest SHA-256: `ff3caa54e7ee11c2bde79e49da5604277d506c826b891fb7a1e4edd04b157c5a`.

## Diagnostic history retained

The A1-A5 failures/blocked runs and D1-D7 diagnostics remain historical evidence.
They are not rewritten by this freeze. In particular, D4 and D7 established the
sampling-policy causes later remediated before A6; A6 is the first authoritative
production runner execution in which the frozen conjunctive propagated gate
passes.

## Boundaries after commit

- `DG_TIME_SCHEDULE / TIME_B_TB2`: MAIN_FROZEN;
- Time Schedule D_GEN runtime use: AUTHORIZED;
- `DG_DISTANCE_PRIOR` real CAL: NOT_AUTHORIZED;
- TEST: SEALED;
- formal G2: NOT_EVALUATED.

No Distance Prior CAL access is authorized by this overlay.
