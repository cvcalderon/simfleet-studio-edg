# F3.4a — Contract-freeze execution instructions

This overlay must be applied on committed HEAD `3a6b0eb3e3ef4ab9311383a418c88d9e9ef20ada`.

F3.4a MUST NOT read CAL rows.

After extraction:

```bash
sha256sum -c docs/F3_4A_OVERLAY_CHECKSUMS_v1.sha256
ruff check scripts/verify_f3_4a_contract.py tests/test_f3_4a_contract.py
pytest -q tests/test_f3_4a_contract.py
pytest -q
python scripts/verify_f3_4a_contract.py
git diff --check
git status --short
```

Stop before `git add`/commit and return the outputs for review.

Do not execute or inspect CAL metrics during F3.4a.
