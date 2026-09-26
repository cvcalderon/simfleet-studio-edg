# SimFleet-EDG — F3.1c Ruff import-order fix v2

**Scope:** mechanical lint-only correction after VM pre-freeze validation.

The VM quality gates confirmed:

- focused F3.1c tests: 8/8 PASS;
- full suite: 69/69 PASS;
- F3.1c verifier: 31/31 PASS;
- Ruff: two `I001` import-order findings only.

This fix changes only import ordering in:

- `scripts/verify_f3_1c_contract.py`;
- `tests/test_f3_1c_contract.py`.

It does **not** modify the F3.1c scientific/design contract, feature subsets, fitting objectives, candidate families, hyperparameter grid, promotion margins, low-support policy, seed policy, CAL protocol, TEST sealing, or formal gate status.

After applying this overlay, rerun the focused tests, full suite, Ruff, and verifier before committing F3.1c.
