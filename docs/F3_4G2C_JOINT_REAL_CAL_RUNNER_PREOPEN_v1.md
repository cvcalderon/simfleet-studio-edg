# F3.4g-2c — Joint Real-CAL Runner PREOPEN v1

## Purpose

Implement the final selected-vs-all-reference CAL runner without opening CAL.

The runner is deliberately inert until it receives a positive external
F3.4g-2b authorization bound to the exact synchronized implementation commit.

## Execution order

The runner must execute in this order:

1. validate external authorization;
2. require `main`, `HEAD == origin/main`, clean worktree;
3. only then create `<output>.partial`;
4. only then open the eight frozen CAL inputs;
5. validate every input by SHA-256 and exact physical row count;
6. resolve and validate the ten frozen pipeline artifact slots;
7. generate SELECTED and ALL_REFERENCE under 32 CRN replicates;
8. calculate frozen Joint metrics;
9. evaluate the frozen Joint gate;
10. write checksummed RunBundle;
11. atomically rename `.partial` to the final output.

A missing or invalid authorization must leave:

```text
CAL files opened = []
CAL rows read = 0
staging created = false
```

## Joint metrics

The runner evaluates the frozen F3.4g-1 matrix.

Participation and Trip Count retain person-day `P_GEW` semantics.

Activity Chain reuses the accepted TRAIN-fitted purpose-attribution primitive
and the accepted propagated chain metric implementation.

For Time and Distance, observed trip targets retain `W_GEW`. Generated trips
inherit the source person-day `fit_weight_P_GEW`, matching the propagated
day-weight semantics already used by Activity Chain. This operational detail is
frozen here before Joint CAL is opened.

No composite score is computed.

## Gate status versus execution status

A scientifically valid execution can produce either Joint PASS or Joint FAIL.

Therefore:

- `run_manifest.status = PASS` means execution/evidence integrity passed;
- `joint_gate.pass_gate` records the scientific gate result;
- Joint FAIL is **not** treated as a runner crash.

Even if the Joint gate passes, this phase does not open TEST. The primitive's
test authorization is recorded only as `test_eligible_by_joint_gate`; actual
`test_open_authorized` remains false until a later explicit MAIN authorization.

## Failure semantics

If failure occurs after positive authorization and staging creation, the
`.partial` directory is preserved with `failure.json` and checksums.

The same authorization must not be reused after such a failure.
