# F3.4f-2c — A1 Closure v1

## A1 status

`F3.4f-2b A1 = FORMALLY CLOSED / PASS`.

The controlled Distance Prior CAL execution was performed once under implementation
commit `1530cac0b4d634eb064bc46d5fb7ee429518d208`. A later verifier-only remediation
at commit `48dddece478e30a5e592f4eda681e0b972df02db` did not rerun CAL. The preserved
RunBundle passed checksum, provenance, boundary, and semantic verification.

## CAL access

The preserved execution opened exactly:

- `person_day_context.csv`: 469 rows;
- `distance_raw.csv`: 1,147 rows;
- `distance_expanded_sensitivity.csv`: 1,257 rows.

Total physical CAL rows read: **2,873**.

TEST rows read: **0**.

## Frozen-rule proposal

The A1 runner proposed:

`DIST_REF_REFERENCE`

with status:

`PROPOSED_BY_FROZEN_CAL_RULES_AWAITING_MAIN_FREEZE`.

This document does not itself perform the MAIN freeze; that decision is recorded
by `F3_4F2C_DISTANCE_PRIOR_MAIN_FREEZE_DECISION_v1.md`.
