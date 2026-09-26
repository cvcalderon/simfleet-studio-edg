# F3.2f — execution instructions v1

1. Verify the live repository is on clean synchronized `main` at the frozen F3.2e implementation commit.
2. Apply this overlay.
3. Verify overlay checksums.
4. Run focused tests, full regression, task-scoped Ruff and `verify_f3_2f_time_schedule_prep.py`.
5. Stop for MAIN pre-commit review.
6. Only after authorization, commit and push.
7. Confirm `artifacts/runs/F3_2f_time_schedule_fit_v1` does not exist.
8. Execute:

```bash
python -m simfleet_edg.repro.f3_2f_fit_time_schedule \
  --config configs/f3/f3_2f_time_schedule_fit_v1.yaml \
  --out artifacts/runs/F3_2f_time_schedule_fit_v1
```

Expected: `status=PASS`, `models_fitted=7`.

Do not read CAL, do not select a candidate, do not open TEST.
