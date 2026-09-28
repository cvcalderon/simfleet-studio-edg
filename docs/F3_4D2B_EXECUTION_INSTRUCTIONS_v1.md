# F3.4d-2b PRE-OPEN execution instructions

1. Apply this overlay to the clean `main` baseline whose HEAD is
   `6ea9abcd7e720d62940933aee12534797440c996`.
2. Verify overlay checksums.
3. Run Ruff on the new Python files.
4. Run the focused F3.4d-2b tests.
5. Run the full regression suite.
6. Run `python scripts/verify_f3_4d2b_preopen.py`.
7. Run `git diff --check` and inspect exact overlay scope.
8. Commit only after every gate passes.
9. Do **not** execute `f3_4d2b_activity_chain_cal` yet. Real CAL requires a new
   external authorization bound to the post-commit HEAD.
10. Do not open TEST and do not authorize `DG_TIME_SCHEDULE`.
