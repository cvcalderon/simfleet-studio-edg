# F1-P_CONSTR-IMPL-02 A1 MAIN Freeze — execution instructions

1. Require clean `main` at the exact implementation commit.
2. Require `origin/main` to match.
3. Require the preserved official A1 RunBundle ZIP and exact SHA256.
4. Apply this overlay.
5. Run Ruff on freeze verifier/test.
6. Run focused freeze tests.
7. Run full regression.
8. Run independent verifier against the preserved RunBundle.
9. Run `git diff --check`.
10. STOP before staging or commit.
