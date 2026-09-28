# F3.4d-2a execution instructions

This phase must not read CAL.

Recommended persistent synthetic RunBundle:

`$HOME/simfleet-edg-runs/F3_4d2a_DG_ACTIVITY_CHAIN_SYNTHETIC_v1`

Execution:

```bash
python -m simfleet_edg.repro.f3_4d2a_activity_chain_preopen   --config configs/f3/f3_4d2a_activity_chain_synthetic_preopen_v1.yaml   --output-dir "$RUN_DIR_AC_SYN"
```

The runner refuses to overwrite an existing final or `.partial` directory.

After execution:
- verify `checksums.sha256`;
- run `scripts/verify_f3_4d2a_preopen.py`;
- stop before staging/commit.

Do not inspect or open CALIBRATION files.
Do not open TEST.
Do not perform candidate selection.
