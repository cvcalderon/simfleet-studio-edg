# F1-P_CONSTR-IMPL-01 — A1 MAIN Freeze v1

## Decision

The preserved official A1 RunBundle for `F1-P_CONSTR-IMPL-01` is accepted by MAIN and proposed for closure as:

`IMPL01_A1_CLOSED_FROZEN`.

## Execution identity

Implementation commit:

`2b08eeb1440c1fd8171917b91047b1b0c6be46f6`

Authoritative RunBundle ZIP SHA256:

`de4e70a07483f594053c2bb6b04e82e8be8d38191e0336bebad3e38186175de0`

The execution was performed on `main`, synchronized with `origin/main`, with a clean worktree.

## Independently rederived evidence

MAIN independently rederived the reconciliation metrics from the RunBundle CSV evidence rather than trusting only the runner summary:

```text
normalized rows             = 4,284
person-domain total         = 3,532,081
Bezirk count                = 12
detail cells                = 1,584
changed detail cells        = 56
Stage 1 L1                  = 161
Stage 2 L1                  = 272
Stage 3 L1                  = 478
max detailed adjustment     = 12
published zero violations   = 0
negative fit cells          = 0
duplicate cube keys         = 0
size 1..5 divisibility errs = 0
all Bezirke feasible        = true
```

The 3,532,081 reconciled persons equal the frozen 1000A-1029 private-household person-domain anchor.

The 38 published `'-'` cells in the detailed 1000A-3082 fit cube remain exact zero after reconciliation.

## Source identity

All five staged source hashes match the frozen IMPL-01 configuration. No raw source bytes are copied into the RunBundle and source bytes are not modified.

## Algorithm freeze

```text
algorithm  = EDG_RECONCILED_PHH_PERSON_CUBE_V1
stage 4    = CANONICAL_WEIGHTED_LINEAR_V1
```

Stage 4 is a deterministic tie-break only. The scientific lexicographic objectives remain Stage 1 → Stage 2 → Stage 3.

## Boundaries

This closure does **not** claim population construction is complete.

Still deferred:

- scale projection (10k / 100k / 1M);
- `6+` household completion;
- P_TRS / HD_U / HD_W population construction;
- CAL candidate comparison;
- G1 holdout evaluation.

Protected boundaries remain:

```text
CAL read          = false
MiD TEST read     = false
1000A-1035 read   = false
F3 modified       = false
G1                = OPEN
G2                = PASS / CLOSED / DO NOT REOPEN
```

## Next step

After this freeze is validated and committed, the next methodological/implementation unit is:

`F1-P_CONSTR-IMPL-02 — scale projection + common 6_PLUS branch`.
