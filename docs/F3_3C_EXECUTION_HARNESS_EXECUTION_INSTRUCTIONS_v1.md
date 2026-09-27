# F3.3c — VM execution instructions

1. Apply overlay on clean synchronized F3.3b parent.
2. Validate overlay checksums.
3. Run `pytest -q tests/test_f3_3c_pre_cal_harness.py`.
4. Run the full test suite.
5. Run task-scoped Ruff.
6. Run `python scripts/verify_f3_3c_pre_cal_harness.py`.
7. Run the safe module entry point.
8. Confirm `git diff --check` and exact overlay scope.
9. Do not stage/commit until MAIN reviews the outputs.
10. Do not open CAL or TEST.
