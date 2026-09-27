# F3.4b-1 — Participation CAL Runner Implementation + Synthetic Dry-Run

**Required parent:** `97691dbec1dee3bd8fbaefd240de512a161a59ad`

## Purpose

Implement the first controlled-CAL runner interface without opening CAL. The dry-run validates two independent layers:

1. the eight frozen TRAIN Participation artifacts can still be instantiated and executed on synthetic context;
2. the metric/CRN/bootstrap/selection/RunBundle plumbing completes end-to-end on synthetic-only evidence.

## Hard boundaries

- CAL partition: `UNOPENED`.
- CAL rows read: `0`.
- TEST partition: `SEALED`.
- TEST rows read: `0`.
- Candidate selection: `NONE`.
- PART_B CAL calibration: forbidden in this phase.
- Downstream D_GEN components: forbidden.
- Formal G2: `NOT_EVALUATED`.

A synthetic preview may exercise the lexicographic selection primitives, but it has no scientific or promotion meaning and must never be persisted as a selected model.

## Frozen execution identities

- component: `DG_PARTICIPATION`;
- artifacts: 8;
- master seed: `20260926`;
- stochastic guardrail replicates: 32;
- household bootstrap replicates: 1000;
- confidence interval: 95%;
- primary metric: weighted Bernoulli log-loss from predictive probabilities;
- guardrails exercised: M2-PART-01 and M2-COND-01 analogues on synthetic evidence.

## Pass condition

F3.4b-1 may close only if the synthetic runner produces the required RunBundle, all frozen Participation artifacts pass synthetic smoke validation, checksums validate, tests/regression pass, and both CAL/TEST row counters remain exactly zero.

During pre-commit validation the synthetic RunBundle must be written outside the repository. A PASS authorizes preparation of F3.4b-2. It does not itself open CAL.
