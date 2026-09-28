# F3.4b-2c execution instructions

1. Apply this overlay on exact parent `d3ad3ba5881cc5629db4b64782441199c6f69df8`.
2. Do not modify or regenerate the F3.4b-2b RunBundle.
3. Run:
   - `sha256sum -c docs/F3_4B2C_OVERLAY_CHECKSUMS_v1.sha256`
   - Ruff on the verifier/test.
   - focused test.
   - full regression.
   - `python scripts/verify_f3_4b2c_main_freeze.py --run-dir "$RUN_DIR"`
   - `git diff --check`
   - `git status --short`
4. Stop before staging and return the outputs to MAIN.
5. This freeze keeps TEST sealed and does not itself authorize DG_TRIP_COUNT.
