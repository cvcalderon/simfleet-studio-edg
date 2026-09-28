# F3.4c-2b Attempt A1 — Failure record

Implementation commit:
`806c1b3e09530645163fc6983b9a76c0baf4efd1`

Authorization:
`F3_4C2B_DG_TRIP_COUNT_REAL_CAL_AUTHORIZATION_V1`

Outcome:
`BLOCKED_IMPLEMENTATION_VALIDATION_AFTER_CAL_OPEN`.

The runner loaded and hash/row-validated the three authorized CAL files:

- `person_day_context.csv`: 469 rows
- `participation.csv`: 460 rows
- `trip_count.csv`: 381 rows

Physical rows read by the failed execution: 1310.

It then failed at the pre-candidate universe equality assertion. The `.partial`
RunBundle was preserved and its internal checksum validation passed.

Candidate evaluation had not begun. Candidate selection remained `NONE`.
TEST remained sealed and G2 remained `NOT_EVALUATED`.

The old authorization must not be reused after remediation because the real runner
is commit-bound.

Preserved failed-attempt witness hashes:

- `failure.json`:
  `3689b1bf3611fe08cd977eec26082e65c133e0fc6840b3cc481316785d1703b1`
- `checksums.sha256`:
  `902465109244b224ad3d7f1d239929e616d9072d271dc371ce9c2156a1837ec9`
