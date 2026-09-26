# F3.2f � Runner Git Identity Remediation v1

## Finding

The first official F3.2f TRAIN-fit attempt aborted before output
creation because the runner incorrectly compared the current Git HEAD
against `expected_parent_commit`.

## Failed pre-output attempt

- implementation commit:
  `128e2232cac3c92d31cdaa38a4c60b4510d1fc69`
- design parent:
  `8aa9af765ed9aa2d69fe797c1530c88ae55ed5f4`
- output creation reached: NO
- CAL consumed: NO
- TEST consumed: NO
- model fitting reached: NO

## Root cause

`expected_parent_commit` identifies the design/implementation parent
from which F3.2f was prepared.

It must not be required to equal the current official implementation
HEAD after F3.2f itself has been committed.

The valid official-run Git guards remain:

- branch = main;
- worktree clean;
- origin/main synchronized.

The current HEAD is recorded by the runner in the generated artifact
manifests as `parent_git_commit`.

## Remediation

Removed the self-invalidating equality:

`state["commit"] == cfg["expected_parent_commit"]`

No data contract, model family, feature set, hyperparameter grid,
temporal rule, TRAIN evidence, CAL boundary, or TEST boundary changed.

## Runner hashes

- before: `14bf516a2c9e9799f31f3699fee6ec6dbc3d004dcd18713c432a56300e1a3f1f`
- after:  `26988be647ea464d0ee8ea7e5a9d22989938b37d87b874a74653bb5cdc1d51dc`

## Classification

`RUNNER_GIT_IDENTITY_GUARD_BUG`

This is an orchestration/provenance remediation, not a scientific
model change.
