# F3.4c-2c execution instructions

This phase does not open CAL or TEST.

1. Apply the overlay on the exact parent commit.
2. Verify overlay checksums.
3. Materialize `docs/F3_4C2C_A2_RUN_WITNESS_v1.json` from the preserved A2
   RunBundle.
4. Run Ruff and focused/full regression.
5. Run `verify_f3_4c2c_main_freeze.py --run-dir <A2 RunBundle>`.
6. Run `git diff --check` and inspect exact scope.
7. Stop before staging/commit and return evidence to MAIN.

Do not rerun F3.4c-2b-A2.
Do not open TEST.
Do not authorize Activity Chain execution.
