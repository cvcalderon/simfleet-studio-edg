# F3.2d — execution instructions v1

1. Apply overlay from repository root.
2. Verify `docs/F3_2d_TRIP_COUNT_OVERLAY_CHECKSUMS_v1.sha256`.
3. Run focused tests, full regression, Ruff, and `scripts/verify_f3_2d_trip_count_prep.py`.
4. Commit/push the implementation while official output is still absent.
5. From clean synchronized `main`, run:

```bash
python -m simfleet_edg.repro.f3_2d_fit_trip_count \
  --config configs/f3/f3_2d_trip_count_fit_v1.yaml \
  --out artifacts/runs/F3_2d_trip_count_fit_v1
```

Never overwrite a failed/accepted output path. Use a distinct retry suffix for a failed execution. TRAIN diagnostics do not authorize model selection. CAL and TEST stay unopened in this phase.
