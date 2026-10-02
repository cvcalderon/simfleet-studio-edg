# F3.4g-1 — Execution instructions v1

Preconditions:

- branch `main`;
- HEAD == origin/main == `5913f9604378cf2356a9251accf59105c51e9163`;
- clean tracked worktree/index;
- all five MAIN freeze witnesses present and exact;
- all selected/reference model artifacts physically present;
- CAL files may be checked for existence only;
- no CAL file content may be read;
- TEST remains sealed.

Validation sequence:

1. apply overlay;
2. Ruff;
3. focused F3.4g-1 tests;
4. full regression;
5. contract verifier;
6. `git diff --check`;
7. exact overlay scope;
8. STOP before staging/commit.
