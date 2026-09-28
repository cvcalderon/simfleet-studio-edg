# F3.4d-2c execution instructions

This phase does not open CAL or TEST.

1. Apply overlay on the required parent commit.
2. Verify static overlay checksums.
3. Run Ruff and focused tests.
4. Run full regression.
5. Verify MAIN Freeze against the existing immutable A1 RunBundle:

```bash
RUN_DIR_AC_A1="$HOME/simfleet-edg-runs/F3_4d2b_A1_DG_ACTIVITY_CHAIN_CAL_v1"

python scripts/verify_f3_4d2c_main_freeze.py   --run-dir "$RUN_DIR_AC_A1"
```

6. Run `git diff --check` and inspect exact overlay scope.
7. Stop before staging/commit.

Do not rerun A1.
Do not open DG_TIME_SCHEDULE CAL.
Do not open TEST.
