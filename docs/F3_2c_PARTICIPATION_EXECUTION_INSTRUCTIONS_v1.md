# F3.2c — DG_PARTICIPATION execution instructions v1

1. Apply overlay at clean/synchronised parent `f6d93061297bf46f1203d4e5f5914a62c95141ec`.
2. Run focused/full pytest, Ruff and `python scripts/verify_f3_2c_participation_prep.py`.
3. Commit/push the implementation before official fitting.
4. Official output path must not already exist.
5. From the clean implementation commit run:

```bash
python -m simfleet_edg.repro.f3_2c_fit_participation \
  --config configs/f3/f3_2c_participation_fit_v1.yaml \
  --out artifacts/runs/F3_2c_participation_fit_v1
```

6. Verify `checksums.sha256`, manifests, eight fitted models, and absence of CAL/TEST metrics/selection.
7. Do not evaluate CAL or TEST in this substep.
