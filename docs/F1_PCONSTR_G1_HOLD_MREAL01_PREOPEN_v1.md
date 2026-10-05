# F1-P_CONSTR-G1 — HOLD-MREAL-001 PREOPEN v1

## Purpose

Resolve only `HOLD-MREAL-001`: materialize the already-selected candidate
`P_CONSTR_RMIN_V2_HD_U` at frozen scale `M` before any `1000A-1035` value I/O.

## Frozen realization

- scale: `M`;
- nominal target: `100000` persons;
- selected candidate: `P_CONSTR_RMIN_V2_HD_U`;
- candidate master seed: `20261005`;
- 6+ master seed: `20261004`;
- donor partition: TRAIN only;
- geography: Bezirk only; PLR remains closed.

The M constrained plan was already frozen by IMPL-03. Its 1..5 branch contains
`54026` households and `93127` persons. The frozen IMPL-02 6+ completion adds
`802` households and `6873` persons, so the materialized M realization must contain
exactly `54828` households and `100000` persons.

## Execution design

The runner reuses the committed IMPL-03 functions. It does not create a new
population algorithm. It performs only:

1. recompute frozen M upstream projection and H6 sizes;
2. load frozen TRAIN donor catalog;
3. reproduce frozen equivalence plan;
4. draw HD_U donors using the existing deterministic seed schedule;
5. materialize the existing common 6+ branch;
6. validate structural/donor/fit anchors;
7. emit core-table hashes for later MAIN freeze.

## Fail-closed authorization

PREOPEN itself cannot execute M. A separate external positive authorization must
be issued only after this runner is committed and pushed. It must bind the exact
synchronized runner commit.

## Absolute boundaries

`1000A-1035` remains unacquired, unread and unauthorized. No holdout metric is
computed. CAL and MiD TEST are not reopened. PLR allocation and F3 remain closed.

`HOLD-THRESH-001` remains OPEN after this phase.
