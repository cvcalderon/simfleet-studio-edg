# F3.4g-2e — PREOPEN execution instructions v1

Required parent: `5992cdc34cd0e729a71e790caa15d839db99475d`

Validation sequence:
1. exact clean synchronized parent;
2. apply overlay;
3. Ruff;
4. focused tests;
5. full regression;
6. verify frozen Joint metric matrix;
7. read only F1 split-assignment manifest metadata;
8. verify manifest SHA/version/seed/household atomicity;
9. verify full split counts `1238/268/264`;
10. derive strict R_min counts `1219/263/260`;
11. verify TEST materialization is deferred;
12. verify tracked TEST authorization remains negative;
13. prove zero TEST outcome content reads;
14. `git diff --check`;
15. exact overlay scope;
16. STOP before staging/commit.

Do not materialize TEST outcome CSVs, hash TEST outcome files, count TEST outcome rows, calculate TEST metrics, or evaluate G2.
