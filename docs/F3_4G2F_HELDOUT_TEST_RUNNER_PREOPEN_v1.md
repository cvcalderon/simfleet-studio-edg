# F3.4g-2f — Held-out TEST Runner PREOPEN v1

## Purpose

Implement the single-use held-out TEST materialization + evaluation runner
without opening TEST outcome content.

## Materialization

The runner does not change the historical F3.2a TRAIN/CAL materializer or its
explicit TEST prohibition.

Instead, after a valid external TEST authorization, it reuses the frozen F3.2a
builder primitives for a separately controlled TEST-only materialization:

- same source manifest;
- same source hashes;
- same household/person loaders;
- same eight table builders;
- same schema;
- same deterministic row-id rule, with partition `TEST`;
- same row-retention semantics;
- same distance provenance semantics.

The F1 split manifest defines TEST membership. Only households satisfying both:

```text
split == TEST
joint_rmin_donor_eligible == true
```

are used. The frozen expected household count is 260.

## Vocabulary

TEST never defines a vocabulary.

The existing TRAIN-fitted vocabulary is frozen semantically in
`f3_4g2f_train_vocabulary_snapshot_v1.json`.

Any TEST category absent from TRAIN is mapped to `__UNSEEN__`.

## First irreversible operation

A valid authorization is required before staging.

After authorization and staging creation, source validation opens the
first protected source.

Immediately after the first non-empty content block is successfully read, the
runner writes:

`holdout_consumption.json`

with `holdout_consumed=true`.

Therefore a failure before any protected-source byte is read leaves the holdout
unconsumed; a failure from the first successfully read content block onward
leaves a persistent consumed-holdout witness.

## TEST generation

SELECTED and ALL_REFERENCE are generated end-to-end under:

- scenario `TEST_EVAL_V1`;
- master seed `20261003`;
- 32 replicates;
- common random numbers.

The TEST runner has its own seed-parameterized generator. It does not reuse the
CAL generator's frozen CAL master seed.

Activity-chain purpose attribution is generated using the same frozen purpose
primitive and a TEST-seed draw schedule.

## Metrics and G2

The 17 Joint metrics are evaluated with the exact F3.4g-1 matrix:

- 14 decision metrics;
- 3 report-only;
- no composite score.

The TEST implementations remove only CAL-specific fixed row-count assertions.
Metric definitions, weights, support rules, and tolerances are unchanged.

A valid execution yields exactly one scientific result:

`G2 = PASS` or `G2 = FAIL`.

Scientific FAIL is not an execution crash and must not trigger tuning or rerun
on the consumed holdout.
