# F3.2g — execution instructions v1

1. Verify clean synchronized `main` at `799d5c6085c7c29ba7e83e02d37b37aac22ee296`.
2. Apply this overlay.
3. Verify overlay checksums.
4. Run focused tests, full regression, task-scoped Ruff and `verify_f3_2g_distance_prior_prep.py`.
5. Stop for MAIN pre-commit review.
6. Only after authorization, commit and push.
7. Confirm `artifacts/runs/F3_2g_distance_prior_fit_v1` does not exist.
8. Execute only after MAIN authorization:

```bash
python -m simfleet_edg.repro.f3_2g_fit_distance_prior   --config configs/f3/f3_2g_distance_prior_fit_v1.yaml   --out artifacts/runs/F3_2g_distance_prior_fit_v1
```

Expected: `status=PASS`, `models_fitted=5`.

Do not read CAL, do not select a candidate, and do not open TEST.
