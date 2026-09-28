# F3.4e-2a Synthetic RunBundle specification

Required files:

- `run_manifest.json`
- `artifact_validation.csv`
- `synthetic_primary_metrics.csv`
- `synthetic_generated_draws.csv`
- `seed_schedule.csv`
- `temporal_validator_smoke.csv`
- `validation.csv`
- `checksums.sha256`

Expected anchors:

- candidate artifacts: 7
- stochastic replicates: 32
- generated draw rows: 224
- synthetic primary rows: 7
- seed rows: 32
- direct temporal-validator smoke rows: 4
- generated temporal invariant violations: 0
- CAL rows read: 0
- TEST rows read: 0
- selection: NONE
- G2: NOT_EVALUATED

`checksums.sha256` covers every RunBundle file except itself.
