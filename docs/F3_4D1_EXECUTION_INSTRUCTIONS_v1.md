# F3.4d-1 local validation

1. Apply this overlay on commit
   `57b54fbbab84ef578154ff55e29656121369c286`.
2. Verify overlay checksums.
3. Run Ruff on the verifier/tests.
4. Run focused tests, then full regression.
5. Run `scripts/verify_f3_4d1_contract.py`.
6. Run `git diff --check` and inspect exact scope.
7. Stop before staging/commit.

Do not read CAL.
Do not execute Activity Chain CAL.
Do not open TEST.
