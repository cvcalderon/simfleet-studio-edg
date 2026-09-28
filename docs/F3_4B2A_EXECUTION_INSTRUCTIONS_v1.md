# F3.4b-2a PRE-OPEN execution instructions

This phase must keep CAL unread.

```bash
sha256sum -c docs/F3_4B2A_OVERLAY_CHECKSUMS_v1.sha256
ruff check src/simfleet_edg/evaluation/participation_cal_real.py src/simfleet_edg/repro/f3_4b2_participation_cal.py scripts/verify_f3_4b2a_preopen.py scripts/verify_f3_4b2_runbundle.py tests/test_f3_4b2_participation_cal.py
pytest -q tests/test_f3_4b2_participation_cal.py
pytest -q
python scripts/verify_f3_4b2a_preopen.py
git diff --check
git status --short
```

Stop before staging/commit. Do **not** invoke the real-CAL CLI in F3.4b-2a. After MAIN pre-commit review, commit the overlay. A separate F3.4b-2b authorization package will then bind the exact commit and provide the first real-CAL command.
