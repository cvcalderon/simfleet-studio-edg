# F3.4g-2g — Held-out TEST A1 Closure / G2 Freeze v1

## Decision

The preserved F3.4g-2f A1 held-out TEST execution is formally closed as:

`HELDOUT_TEST_A1_CLOSED_G2_PASS`.

## Execution integrity

The execution is bound to implementation commit:

`911abb2ee194d9c3529880f26ba4773eb82c821d`

and authorization:

`F3_4G2F_A1_HELDOUT_TEST_SINGLE_USE_V1`.

Authoritative evidence:

- strict TEST households: 260;
- source hashes: 13/13 PASS;
- TEST tables materialized: 8;
- frozen pipeline artifact slots: 10/10 PASS;
- stochastic replicates: 32;
- TEST seed: 20261003;
- generated person-day rows: 29,632;
- generated trip rows: 95,046;
- candidate selection: NONE;
- issues: none;
- recursive RunBundle checksums: PASS;
- holdout consumed: true.

## Formal G2

All 14 decision-driving metrics pass.

The three report-only metrics remain non-decision evidence.

Hard invariants:

```text
structural = 0
temporal   = 0
NoFuture   = 0
```

Therefore:

`formal G2 = PASS`.

## Metric interpretation

The decision thresholds are maximum permitted worsening versus the frozen
ALL_REFERENCE comparator. They are not absolute-error targets.

The closest decision metric to its materiality threshold is:

```text
metric      = M2-CHAIN-01
worsening   = 0.000427683
threshold   = 0.005000000
headroom    = 0.004572317
```

It remains within the preregistered threshold.

This closure therefore supports the claim:

`the frozen SELECTED pipeline does not materially degrade the frozen
ALL_REFERENCE comparator on the single-use held-out TEST under the
preregistered G2 decision rule`.

It does not imply that every absolute error is small.

## Holdout finality

The TEST holdout is consumed.

```text
same holdout rerun authorized = false
post-TEST tuning authorized   = false
same authorization rerun      = false
```

This result is terminal for this holdout.

## G1 remains separate

G2 PASS does not resolve the pre-existing G1 source blocker.

Current high-level status:

```text
G1 = OPEN
G2 = PASS
```
