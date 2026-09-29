# F3.4e-2b — A2 failure analysis

A2 reached isolated candidate evaluation and stopped at `TIME_REF failed isolated temporal hard invariant`.

Reconstruction against the frozen TRAIN/CAL material shows the reference sampler is not accepting invalid rows. The failure comes from the finite `MAX_REJECTION_ATTEMPTS=100` cap used while drawing from the global empirical temporal support under late-day temporal constraints.

Anchors from deterministic reconstruction:

- CAL isolated rows: 1243
- CRN replicates: 32
- TIME_REF finite-rejection exhaustions: 95
- affected CAL rows: 10
- affected person-days: 9
- worst-row feasible TRAIN-support probability: approximately 0.003423
- corresponding probability of exhausting 100 independent attempts: approximately 0.7097

The hard gate therefore mixed two distinct events: (a) accepting an invalid generated temporal row, and (b) failing to obtain an otherwise feasible sample within an arbitrary finite retry budget.

## Remediation

For TIME_REF only, real-CAL evaluation now samples directly from the frozen empirical support conditioned on the frozen temporal state:

1. evaluate every frozen `(departure,duration)` support point with `validate_temporal_row`;
2. retain only feasible support points;
3. renormalize their original frozen probabilities;
4. sample once using the existing candidate-independent CRN seed;
5. fail hard if and only if feasible support is genuinely empty.

This distribution is the exact conditional distribution induced by rejection sampling given eventual acceptance. It does not repair a draw, invent a value, alter the TRAIN support, introduce candidate ID into the RNG key, read TEST, or authorize Distance Prior CAL.

The same TIME_REF rule is used in isolated and propagated evaluation so the guardrail semantics are consistent.
