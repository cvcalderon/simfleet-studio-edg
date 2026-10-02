# F3.4f-2c — Execution Instructions v1

This overlay freezes `DIST_REF_REFERENCE` as the MAIN-selected Distance Prior
artifact. It does **not** rerun CAL and does not read CAL source files.

Preconditions:

- branch `main`;
- HEAD and `origin/main` exactly
  `48dddece478e30a5e592f4eda681e0b972df02db`;
- clean worktree/index before overlay application;
- preserved A1 RunBundle available at
  `$HOME/Downloads/F3_4f2b_A1_distance_prior_real_cal_run_v1`.

Validation:

1. Ruff;
2. focused tests;
3. full regression;
4. `scripts/verify_f3_4f2c_main_freeze.py --run-dir <preserved A1 RunBundle>`;
5. `git diff --check`;
6. exact overlay scope.

STOP before staging/commit. MAIN review is required.
