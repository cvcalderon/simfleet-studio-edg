# F3.2e — execution instructions v1

1. Start from synchronized `main` at `a69389d904c526c1b8c320f4354b42ab9bfa7a18` with a clean worktree.
2. Apply the F3.2e overlay from repository root.
3. Verify `docs/F3_2e_ACTIVITY_CHAIN_OVERLAY_CHECKSUMS_v1.sha256`.
4. Run focused tests, full regression, Ruff, and `scripts/verify_f3_2e_activity_chain_prep.py`.
5. Commit/push the implementation while the official F3.2e output path is still absent.
6. **Do not run the official fit before the implementation commit is synchronized.**
7. From clean synchronized `main`, run:

```bash
python -m simfleet_edg.repro.f3_2e_fit_activity_chain \
  --config configs/f3/f3_2e_activity_chain_fit_v1.yaml \
  --out artifacts/runs/F3_2e_activity_chain_fit_v1
```

Never overwrite a failed or accepted output path. A failed execution must use a distinct retry suffix after root cause/remediation is documented.

TRAIN diagnostics do not authorize candidate selection. CAL fitting/scoring/selection remains disabled in F3.2e. TEST remains sealed.
