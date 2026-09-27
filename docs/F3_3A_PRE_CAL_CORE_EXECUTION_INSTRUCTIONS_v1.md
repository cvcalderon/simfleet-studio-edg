# F3.3a PRE-CAL Core — execution instructions

1. Confirm clean synced `main` at `a128dd29ca4d3d99545039c458ddac68159b592f`.
2. Apply overlay.
3. Validate overlay checksums.
4. Run focused tests and full regression.
5. Run task-scoped Ruff.
6. Run `python scripts/verify_f3_3a_pre_cal_core.py`.
7. Run `python -m simfleet_edg.repro.f3_3_pre_cal_core --config configs/f3/f3_3_pre_cal_core_v1.yaml`.
8. Stop before staging. Send outputs for MAIN PreCommit audit.

Do not read CAL tables and do not open TEST.
