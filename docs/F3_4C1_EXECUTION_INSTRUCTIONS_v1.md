# F3.4c-1 execution instructions

Apply only on exact parent:
`5169dd6e966e4ed55962c4bbba513f442d3c3f15`.

Run:

1. `sha256sum -c docs/F3_4C1_OVERLAY_CHECKSUMS_v1.sha256`
2. Ruff on `scripts/verify_f3_4c1_trip_count_contract.py` and its test.
3. Focused pytest.
4. Full pytest regression.
5. `python scripts/verify_f3_4c1_trip_count_contract.py`
6. `git diff --check`
7. `git status --short`

Stop before staging.

The verifier must not open or parse CAL CSV rows. F3.4c-1 authorizes no real Trip
Count CAL execution.
