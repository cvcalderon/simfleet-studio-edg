# F3.3d — Execution Instructions v1

1. Apply this overlay on clean synchronized commit `a4f650165f6e9f89b2d72fededec559a81bd30f8`.
2. Validate the overlay checksum manifest.
3. Run the focused F3.3d tests.
4. Run the full regression suite.
5. Run task-scoped Ruff.
6. Run `python scripts/verify_f3_3d_pre_cal_entry_gate.py`.
7. Run the safe F3.3d module entry point.
8. Confirm `git diff --check` and exact overlay scope.
9. Do not open CAL yet.
10. MAIN reviews the verifier output.
11. Only after MAIN records `PRE-CAL ENTRY GATE = PASS` may the controlled CAL runner be enabled.
12. TEST remains sealed.
