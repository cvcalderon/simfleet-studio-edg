# F3.3b PRE-CAL execution instructions v1

Required parent commit:

`d79c215bcd938d772c5ee494ed62320045f4b4dc`

Run before staging:

```bash
sha256sum -c docs/F3_3B_CAL_ADAPTERS_OVERLAY_CHECKSUMS_v1.sha256
pytest -q tests/test_f3_3b_cal_adapters.py
pytest -q
ruff check src/simfleet_edg/evaluation/cal_adapter_common.py src/simfleet_edg/evaluation/cal_state.py src/simfleet_edg/evaluation/participation_adapter.py src/simfleet_edg/evaluation/trip_count_adapter.py src/simfleet_edg/evaluation/activity_chain_adapter.py src/simfleet_edg/evaluation/time_schedule_adapter.py src/simfleet_edg/evaluation/distance_prior_adapter.py src/simfleet_edg/evaluation/cal_adapter_factory.py src/simfleet_edg/repro/f3_3b_pre_cal_adapters.py scripts/verify_f3_3b_pre_cal_adapters.py tests/test_f3_3b_cal_adapters.py notebooks/15_f3_3b_pre_cal_adapters.ipynb
python scripts/verify_f3_3b_pre_cal_adapters.py
python -m simfleet_edg.repro.f3_3b_pre_cal_adapters --config configs/f3/f3_3b_cal_adapters_v1.yaml
git diff --check
git status --short
```

Do not stage, commit, inspect CAL, or open TEST until the PreCommit gate is reviewed.
