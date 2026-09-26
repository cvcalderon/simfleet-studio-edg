# F3.1c — Seed and reproducibility contract v1

Master seed: `20260926`.

Runtime draw stream (inherits F3.1b):

`SHA256(master_seed | scenario_id | generated_person_id | component_namespace | draw_index) -> uint64`

The same component random uniforms are used across competing candidates during CAL (common random numbers). Candidate implementations must sort categorical/empirical support by canonical lexical key before cumulative weighted sampling.

Fit randomness is separate and deterministic:

`SHA256("F3_1C" | master_seed | candidate_id | grid_id | "FIT") -> uint32`

Every fitted artifact records parent Git commit, config/source/split hashes, row counts, semantic feature set and vocabulary hash, weight policy, fit seed, library versions, serialized model SHA-256, CAL metrics/bootstrap, backoff/calibration policy and selection decision.

Failed fitting/evaluation attempts are preserved with distinct attempt ids; accepted artifacts never overwrite failed attempts.
