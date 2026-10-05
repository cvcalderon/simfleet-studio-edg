# F1-P_CONSTR-IMPL-03 — execution instructions v1

1. Required parent: `2f547ec53501245af1d605a866e19febfc5089b8` on `main`, synchronized with `origin/main`, clean worktree.
2. Apply the PREOPEN overlay.
3. Run overlay checksums.
4. Run focused IMPL-03 tests.
5. Run full regression.
6. Run Ruff on IMPL-03 files.
7. Run `scripts/verify_f1_pconstr_impl03_prep.py`.
8. Run `git diff --check` and inspect `git status --short`.
9. STOP before staging/commit and return the complete evidence to MAIN.

Forbidden during PREOPEN: CAL, MiD TEST values, `1000A-1035`, PLR allocation, candidate selection, G1 threshold tuning, F3 changes.
