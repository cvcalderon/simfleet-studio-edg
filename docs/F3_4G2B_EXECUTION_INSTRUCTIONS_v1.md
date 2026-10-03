# F3.4g-2b — Execution instructions v1

Required parent:

`30c6340baccac11555800b77d12c4f6d80a89392`

Validation sequence:

1. require exact clean synchronized parent;
2. apply overlay;
3. Ruff;
4. focused tests;
5. full regression;
6. PREOPEN verifier;
7. negative-authorization zero-I/O proof;
8. `git diff --check`;
9. exact overlay scope;
10. STOP before staging/commit.

This phase may check future CAL file **existence only**. It must not read CAL
content, calculate input hashes, parse rows, or create a real-CAL RunBundle.
