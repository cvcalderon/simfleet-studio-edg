# F3.2f — Fit Validation Gate Remediation v1

## Finding

The second official F3.2f TRAIN-fit attempt reached model fitting and wrote the seven
model artifacts plus intermediate summaries, but aborted before the final run manifest.

The validation dictionary represented the observed state:

`test_partition_consumed = false`

which is the required scientific boundary. The runner then incorrectly evaluated
`all(fit_checks.values())`, treating this expected false value as a failed validation.

## Classification

`FIT_VALIDATION_EXPECTED_FALSE_SEMANTICS_BUG`

This is an orchestration/validation bug, not a model, data, CAL, or TEST failure.

## Attempt classification

- attempt 01: `ABORTED_PRE_OUTPUT` — Git identity guard bug.
- attempt 02: `ABORTED_POST_FIT_PRE_MANIFEST` — expected-false validation bug.
- attempt 02 is not an official accepted RunBundle.
- its partial output must be preserved separately and the official output path cleared
  by moving, not deleting, the partial directory.

## Remediation

A helper `_fit_check_passed(check, value)` now gives
`test_partition_consumed` the frozen expected value `false`; all other current boolean
fit checks retain expected value `true`.

The emitted `fit_validation.csv` preserves the established external semantics:

`test_partition_consumed,PASS,false`

No scientific contract, model family, feature set, hyperparameter, TRAIN evidence,
CAL boundary, TEST boundary, or temporal-generation rule is changed.

A focused regression test protects both expected-true and expected-false semantics.
