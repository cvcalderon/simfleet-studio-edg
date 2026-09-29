# F3.4e-2c execution instructions

This phase performs no new CAL execution and opens no TEST data.

1. Apply the overlay only on its exact required parent commit.
2. Verify static overlay checksums.
3. Run Ruff on the freeze verifier and focused test file.
4. Run the focused F3.4e-2c tests.
5. Run the full regression.
6. Verify MAIN Freeze against the existing immutable A6 RunBundle:

```bash
RUN_DIR_TS_CAL_A6="$HOME/simfleet-edg-runs/F3_4e2b_DG_TIME_SCHEDULE_REAL_CAL_A6_v1"
python scripts/verify_f3_4e2c_main_freeze.py --run-dir "$RUN_DIR_TS_CAL_A6"
```

7. Audit exact overlay scope and `git diff --check`.
8. Stop before staging/commit and review the gate output.

Do not rerun A6. Do not open Distance Prior CAL. Do not open TEST. Do not
evaluate G2.
