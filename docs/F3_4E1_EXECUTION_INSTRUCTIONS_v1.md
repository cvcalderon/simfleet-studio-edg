# F3.4e-1 execution

1. Apply overlay on the exact parent.
2. Verify overlay checksums.
3. Run Ruff.
4. Run focused tests.
5. Run full regression.
6. Run `python scripts/verify_f3_4e1_contract.py`.
7. Run `git diff --check` and inspect exact scope.
8. Stop before staging.

Do not open CAL time_trips, Distance Prior CAL, or TEST.
