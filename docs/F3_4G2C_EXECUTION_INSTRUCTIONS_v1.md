# F3.4g-2c — PREOPEN execution instructions v1

Required parent:

`b0ee17a17eb6c58d655b770780cbb40e07b9b33b`

PREOPEN validation must:

1. apply the overlay on an exact clean synchronized parent;
2. run Ruff;
3. run focused tests;
4. run full regression;
5. verify frozen files/hashes and zero-CAL state;
6. invoke the real runner with the tracked negative authorization template;
7. prove the runner rejects before CAL I/O and before staging creation;
8. run `git diff --check`;
9. verify exact overlay scope;
10. STOP before staging/commit.

No positive authorization is included in this package.
