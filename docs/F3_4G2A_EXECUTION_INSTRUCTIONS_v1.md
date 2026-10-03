# F3.4g-2a — Execution instructions v1

Required parent:

`19e903ffbc4cb914d2b70d637bae2e82d1200e30`

Preconditions:

- branch `main`;
- HEAD == origin/main == required parent;
- clean tracked worktree and index;
- F3.4g-1 Joint contract present;
- all 10 pipeline slots resolvable to frozen TRAIN artifacts;
- future CAL files may be checked for existence only;
- no CAL file content may be read;
- TEST remains sealed.

Validation sequence:

1. apply overlay;
2. Ruff;
3. focused tests;
4. full regression;
5. PREOPEN verifier;
6. execute synthetic Joint RunBundle in `~/Downloads`;
7. verify RunBundle;
8. `git diff --check`;
9. exact overlay scope;
10. package RunBundle;
11. STOP before staging/commit.

This PRE-COMMIT RunBundle is development evidence. After commit, rerun the same
synthetic workflow from the authoritative implementation commit before using it
as authoritative PREOPEN evidence.
