# F3.4b-1 execution instructions

Run only after confirming HEAD equals the required parent and the worktree is clean.

```bash
sha256sum -c docs/F3_4B1_OVERLAY_CHECKSUMS_v1.sha256
ruff check src/simfleet_edg/evaluation/participation_cal_dryrun.py src/simfleet_edg/repro/f3_4b1_participation_dryrun.py scripts/verify_f3_4b1_participation_dryrun.py tests/test_f3_4b1_participation_dryrun.py
pytest -q tests/test_f3_4b1_participation_dryrun.py
pytest -q
rm -rf /tmp/SimFleet_EDG_F3_4b1_Participation_DryRun_v1
python -m simfleet_edg.repro.f3_4b1_participation_dryrun --config configs/f3/f3_4b1_participation_cal_runner_dryrun_v1.yaml --output-dir /tmp/SimFleet_EDG_F3_4b1_Participation_DryRun_v1
sha256sum -c /tmp/SimFleet_EDG_F3_4b1_Participation_DryRun_v1/checksums.sha256
python scripts/verify_f3_4b1_participation_dryrun.py
git diff --check
git status --short
```

Stop before `git add` / `git commit` and before any CAL reader is introduced or executed.

The dry-run RunBundle is intentionally written outside the repository during pre-commit validation so it cannot contaminate overlay scope.
