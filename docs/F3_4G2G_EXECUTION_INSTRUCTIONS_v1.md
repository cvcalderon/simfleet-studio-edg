# F3.4g-2g — Closure validation instructions v1

Required parent:

`911abb2ee194d9c3529880f26ba4773eb82c821d`

Required preserved RunBundle:

`$HOME/Downloads/F3_4g2f_A1_heldout_test_run_v1`

This phase must not reopen MiD/F0 protected sources and must not rerun TEST.

Validation sequence:

1. exact clean synchronized parent;
2. apply closure overlay;
3. Ruff;
4. focused tests;
5. full regression;
6. verify preserved RunBundle recursive checksums;
7. verify 13/13 source-hash evidence from RunBundle;
8. verify 8 materialized TEST table hashes from RunBundle;
9. verify 10/10 artifact slots;
10. verify 17 metrics, 14/14 decisions PASS, 3 report-only;
11. verify G2=PASS and hard invariants zero;
12. verify holdout consumed and rerun/tuning forbidden;
13. `git diff --check`;
14. exact overlay scope;
15. STOP before staging/commit.
