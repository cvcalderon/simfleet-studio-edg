# F3.4e-2a execution instructions

## Local validation before execution

```bash
sha256sum -c docs/F3_4E2A_OVERLAY_CHECKSUMS_v1.sha256

ruff check \
  src/simfleet_edg/repro/f3_4e2a_time_schedule_synthetic.py \
  scripts/verify_f3_4e2a_time_schedule_synthetic.py \
  tests/test_f3_4e2a_time_schedule_synthetic_preopen.py

pytest -q tests/test_f3_4e2a_time_schedule_synthetic_preopen.py
pytest -q
python scripts/verify_f3_4e2a_preopen.py
```

## Synthetic execution

```bash
RUN_ROOT="$HOME/simfleet-edg-runs"
RUN_DIR_TS_SYN="$RUN_ROOT/F3_4e2a_DG_TIME_SCHEDULE_SYNTHETIC_v1"

mkdir -p "$RUN_ROOT"
test ! -e "$RUN_DIR_TS_SYN"

python -m simfleet_edg.repro.f3_4e2a_time_schedule_synthetic \
  --config configs/f3/f3_4e2a_time_schedule_synthetic_preopen_v1.yaml \
  --output-dir "$RUN_DIR_TS_SYN"
```

## RunBundle validation

```bash
cd "$RUN_DIR_TS_SYN"
sha256sum -c checksums.sha256
cd ~/Projects/simfleet-studio-edg

python scripts/verify_f3_4e2a_time_schedule_synthetic.py \
  --run-dir "$RUN_DIR_TS_SYN"
```

Do not open CAL.
Do not authorize real Time Schedule CAL.
Do not open Distance Prior CAL.
Do not open TEST.
