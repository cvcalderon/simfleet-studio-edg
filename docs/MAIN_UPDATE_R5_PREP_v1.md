# MAIN update — R5 preparation v1

## Status

R5 implementation package is ready for repository quality gates. Official execution is not authorized until tests, Ruff and `verify_r5_prep.py` pass on a clean synchronized commit.

## Frozen R5 anchors

- D_REPLAY rows: 100,000
- complete replay: 65,963 (65.963%)
- trip intents: 194,457
- strict TRAIN source person-days: 2,200
- full-day source donors: 1,658 = 261 zero-trip + 1,397 mobile

Exact historical primary hashes are frozen in `configs/reproduction/r5_d_replay.yaml`.

## Scope boundary

R5 does not reproduce D_MATCH or the combined F2.1 bridge hash. Those remain R6 scope. G1 remains OPEN; G2 remains NOT CLOSED.
