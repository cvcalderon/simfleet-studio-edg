# F4.2b-B — Worker installation and exact PRE-COMMIT boundary

Implementation from MAIN Worker PREOPEN v1. **Do not modify 19 baseline protected paths, nor any other previously tracked path.** Git `HEAD=origin/main=1fdfd815fb5085cbc674b66baecd932a9bcabff9` on a clean `main` was independently reported PASS. Recheck immediately before installing the overlay.

The 25 new paths are in `F4_2B_B_OVERLAY_FILELIST_v1.txt`. Baseline Ruff/mypy diagnostics are preexisting and must be compared differentially (no new diagnostics). The entry verifies *exactly* 25 untracked paths; 19 fixed protected hashes; the complete 25+19 previous overlay checksums, with only six individually authorized Git LF → original CRLF byte reconstructions; no generic waiver.

Run after copying all 25 new files and before staging:

```bash
python scripts/verify_f4_2b_b_preopen.py --repo "$HOME/Projects/simfleet-studio-edg"
pytest -q tests/test_f4_2b_b_*.py
ruff check src/simfleet_edg/spatial/escort_partial_day_index.py src/simfleet_edg/spatial/escort_day_binding.py src/simfleet_edg/spatial/escort_partial_integration.py src/simfleet_edg/spatial/escort_partial_ledger.py src/simfleet_edg/repro/f4_2b_b_partial_integration.py scripts/verify_f4_2b_b_preopen.py scripts/verify_f4_2b_b_runbundle.py tests/test_f4_2b_b_*.py
mypy src/simfleet_edg/spatial/escort_partial_day_index.py src/simfleet_edg/spatial/escort_day_binding.py src/simfleet_edg/spatial/escort_partial_integration.py src/simfleet_edg/spatial/escort_partial_ledger.py src/simfleet_edg/repro/f4_2b_b_partial_integration.py
pytest -q
```

Run Ruff/mypy *global* fingerprint differential against `$HOME/F4_2B_B_BASELINE_QUALITY_FINGERPRINT.json`, not raw tool exit status. Only after successful focused tests, scoped quality, global differential, full regression, and verifier audit, STOP **PRE-COMMIT**. The user manually commits/pushes from PyCharm.

After manual push and only with new clean `HEAD=origin/main` direct parent the previously frozen commit, the official runner accepts `--stage precheck|single|full`. It requires `--repo --population --c-output --f4a-tar --b2a-tar --f4a-dir --b2a-dir --output`. The TARs are original SHA verified, and extracted immutable results are cross-checked against their internal manifests. `single` is a diagnostic one-pass with all eleven variants; full produces independent complete A/B runs and a verifier-checked RunBundle. Never launch A/B before the exact Git postpush gate PASS. Never touch CAL, MiD TEST, G3 or F4.2c.

This design is *hypothetical location-only*, not observed linkage, co-travel, travel mode, causal validation, or scientific policy selection. All 100,000 days / 325,613 trips per variant remain represented; CORE is immutable by reference; 18,871 original B2-A events per variant remain frozen by reference.
