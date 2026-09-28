# F3.4c-2a execution instructions

Apply only on exact parent:
`5b29b668a2e4367c11661c70dbd15beb27070377`.

Run:

1. overlay checksum verification;
2. Ruff;
3. focused tests;
4. full regression;
5. synthetic/TRAIN pre-open runner to a temporary output directory;
6. verify the synthetic bundle checksums;
7. PRE-OPEN verifier;
8. `git diff --check`;
9. `git status --short`.

Stop before staging.

Do not execute `f3_4c2_trip_count_cal` in this phase. The real runner requires a
future commit-bound F3.4c-2b authorization.
