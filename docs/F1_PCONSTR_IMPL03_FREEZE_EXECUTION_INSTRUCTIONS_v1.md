# F1-P_CONSTR-IMPL-03 A1 MAIN Freeze — execution instructions

1. Require clean `main` at the exact IMPL-03 implementation commit.
2. Require `origin/main` to match.
3. Require the preserved official A1 RunBundle ZIP and exact SHA256.
4. Apply this overlay.
5. Verify freeze-overlay checksums.
6. Run Ruff on freeze verifier/test.
7. Run focused freeze tests.
8. Run full regression.
9. Run independent freeze verifier against the preserved RunBundle.
10. Run `git diff --check`.
11. STOP before staging or commit.

No CAL, MiD TEST, 1000A-1035, PLR, candidate selection, G1 threshold tuning, or F3 access is authorized by this freeze overlay.
