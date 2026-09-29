# F3.4e-2b PRE-OPEN execution instructions

1. Apply this overlay to clean synchronized `main` at
   `fc238749d5972ee189f3223affd8f4daa9f2b186`.
2. Verify overlay checksums.
3. Run Ruff on the new Python files.
4. Run the focused F3.4e-2b tests.
5. Run the full regression suite.
6. Run `python scripts/verify_f3_4e2b_preopen.py`.
7. Run `git diff --check` and audit exact overlay scope.
8. Commit only after every PRE-OPEN gate passes.
9. Do **not** execute `f3_4e2b_time_schedule_cal` yet. Real CAL requires a
   separate external authorization bound to the post-commit HEAD.
10. Do not open TEST and do not authorize Distance Prior real CAL.
