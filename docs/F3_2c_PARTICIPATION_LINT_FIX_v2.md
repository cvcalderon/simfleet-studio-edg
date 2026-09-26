# F3.2c Participation — lint fix v2

## Scope

Preparation-only correction after the F3.2c participation overlay passed focused tests, full regression and the scientific preflight verifier but Ruff reported two unused imports in the official-fit runner.

## Changes

Only `src/simfleet_edg/repro/f3_2c_fit_participation.py` is modified:

- remove unused standard-library import `hashlib`;
- remove unused import `encoder_sha256` from `simfleet_edg.demand.participation`.

No model family, hyperparameter, objective, feature, seed, data hash, TRAIN universe, CAL/TEST policy, output schema, fitting logic or serialization logic is changed.

The ignored `__pycache__/*.pyc` members accidentally present in overlay v1 are not part of this fix and must not be staged; repository ignore rules already exclude them.
