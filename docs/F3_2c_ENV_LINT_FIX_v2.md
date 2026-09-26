# F3.2c environment declaration — lint fix v2

## Scope

Minimal non-semantic correction after VM validation of `SimFleet_EDG_F3_2c_Modeling_Env_Overlay_v1.zip`.

The VM reported one Ruff `I001` import-order violation in:

- `scripts/verify_f3_2c_env.py`

This fix only reorders Python standard-library imports. It does not change:

- the `modeling` optional dependency declarations;
- `.gitignore` policy;
- F3.2b materialized data;
- TRAIN/CAL/TEST semantics;
- runtime dependency requirements;
- verifier logic or phase semantics;
- any scientific/modeling decision.

The original overlay v1 checksum remains historical evidence. This v2 fix supersedes only the affected Python file bytes.
