# F1-P_CONSTR-IMPL-01 — PRE-COMMIT execution instructions v1

## Required parent

```text
15b2fa7a8a0a8dc5e8a8518a284350f2d35d0902
```

Start from clean `main`. Do not commit before MAIN reviews the PRE-COMMIT evidence.

## Source staging

The repository does not track raw research data. Stage the five frozen flat ZIPs from the two downloaded outer bundles:

```bash
python scripts/stage_f1_pconstr_sources.py \
  --phh-bundle "$HOME/Downloads/Zensus_2022_1029_2070_2071_3082(1).zip" \
  --hh-bundle "$HOME/Downloads/5000H-1001.zip"
```

If your download names differ, change only the two paths. The internal flat ZIP SHA256 values are frozen in the script and config.

## PRE-COMMIT validation

From the repository root, with the project virtual environment active:

```bash
sha256sum -c docs/F1_PCONSTR_IMPL01_OVERLAY_CHECKSUMS_v1.sha256

python -m pytest -q \
  tests/test_f1_pconstr_age_projection.py \
  tests/test_f1_pconstr_zensus_controls.py \
  tests/test_f1_pconstr_reconciliation.py \
  tests/test_f1_pconstr_impl01_config.py

python -m pytest -q

python -m ruff check \
  src/simfleet_edg/population/age_projection.py \
  src/simfleet_edg/population/zensus_controls.py \
  src/simfleet_edg/population/reconciliation.py \
  src/simfleet_edg/repro/f1_pconstr_impl01_reconcile.py \
  scripts/stage_f1_pconstr_sources.py \
  scripts/verify_f1_pconstr_impl01_prep.py \
  tests/test_f1_pconstr_age_projection.py \
  tests/test_f1_pconstr_zensus_controls.py \
  tests/test_f1_pconstr_reconciliation.py \
  tests/test_f1_pconstr_impl01_config.py

python scripts/verify_f1_pconstr_impl01_prep.py \
  --config configs/f1/f1_pconstr_impl01_reconciliation_v1.yaml

git diff --check
git status --short
```

## STOP

Send the complete terminal output to MAIN. Do **not** run `git add`, `git commit`, official execution, CAL, TEST, or any held-out source acquisition yet.

The official post-commit command is documented in the codebase but is not authorized by this PRE-COMMIT overlay.
