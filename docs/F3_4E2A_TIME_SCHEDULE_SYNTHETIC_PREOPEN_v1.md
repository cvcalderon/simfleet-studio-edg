# F3.4e-2a — Time Schedule Synthetic PRE-OPEN v1

## Purpose

This phase is a reversible smoke execution of the already-frozen Time Schedule
CAL machinery. It validates frozen artifact loading, adapter sampling, CRN
seed construction, M2-TIME-01 metric primitives, temporal invariants and
RunBundle integrity **without reading CAL or TEST**.

It is not a scientific evaluation and cannot select a candidate.

## Candidate scope

Exactly seven TRAIN-fitted Time Schedule artifacts are exercised:

- TIME_REF_REFERENCE
- TIME_A_TA1
- TIME_A_TA2
- TIME_A_TA3
- TIME_B_TB1
- TIME_B_TB2
- TIME_B_TB3

Each artifact is validated through the frozen `ArtifactRecord.validate()`
hash checks before sampling.

## Synthetic state construction

No empirical CAL state is used.

- TIME_REF receives a one-row placeholder frame because the reference sampler
  does not consume contextual columns.
- TIME_A receives a deterministic synthetic state constructed from the first
  directly eligible cell in its frozen first backoff level.
- TIME_B receives a deterministic synthetic state from its TRAIN-frozen
  encoder manifest: the first non-reserved TRAIN category per categorical
  feature and `0.0` for numeric features.

This is only an adapter smoke test. These synthetic states are not data and
must never be interpreted as calibration evidence.

## CRN

The 32 seeds are generated once from:

- master seed 20260926;
- scenario `CAL_EVAL_V1`;
- generated person `SYNTHETIC_TIME_PERSON`;
- namespace `DG_TIME_SCHEDULE::TRIP::1`;
- draw indices `0..31`.

The same seed vector is supplied to all seven candidates. Candidate identity
is not part of the RNG key.

## Metric smoke

For each artifact, 32 generated departures are transformed to hour bins and
compared against a fixed synthetic 32-observation hour vector using the
already-frozen:

- `weighted_distribution`;
- `total_variation_distance`.

The resulting synthetic TVD is written for traceability only. It cannot drive
candidate selection or promotion.

## Temporal invariant smoke

Every generated draw is independently passed through `validate_temporal_row`.

The runner additionally proves that four intentionally invalid synthetic rows
are rejected:

1. departure below zero;
2. duration zero;
3. departure before previous absolute arrival;
4. a non-final trip crossing midnight.

Required invariant violations among generated draws: zero.

## RunBundle

The runner writes a persistent synthetic RunBundle containing:

- `run_manifest.json`
- `artifact_validation.csv`
- `synthetic_primary_metrics.csv`
- `synthetic_generated_draws.csv`
- `seed_schedule.csv`
- `temporal_validator_smoke.csv`
- `validation.csv`
- `checksums.sha256`

No selection output is produced.

## Boundaries

After PASS:

- CAL rows read = 0;
- TEST rows read = 0;
- candidate selection = NONE;
- Time Schedule real CAL remains unauthorized;
- Distance Prior real CAL remains unauthorized;
- G2 remains NOT_EVALUATED.
