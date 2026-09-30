# F3.4f-1 execution

1. Apply this overlay on exact parent `1c5ec66e4b15553996e473f46c921339f55b30d2`.
2. Do not read/hash/open Distance CAL file contents.
3. Run Ruff on changed Python files.
4. Run focused F3.4f-1 tests.
5. Run full regression.
6. Run `python scripts/verify_f3_4f1_contract.py`.
7. Run `git diff --check` and inspect exact scope.
8. Stop before staging or commit.

Do not open real Distance CAL and do not open TEST.
