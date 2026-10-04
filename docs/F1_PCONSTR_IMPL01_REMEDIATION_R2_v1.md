# F1-P_CONSTR-IMPL-01 — Post-commit remediation R2 v1

**Date:** 2026-10-04
**Parent commit:** `c393a6fb8dc53d6413822a5465f6cab1f4d3c61e`
**Scope:** documentation/checksum hygiene only

## Trigger

The authorized IMPL-01 commit was created and pushed after all functional gates passed, but the staged `git diff --cached --check` output had reported three trailing-whitespace findings in `docs/F1_PCONSTR_FINAL_DESIGN_FREEZE_v1.md`.

## Decision

Do not rewrite published history. Apply a new linear remediation commit before official IMPL-01 execution.

## Changes

1. Replace the three Markdown trailing-space hard breaks with explicit `<br>` markers.
2. Add this R2 traceability note.
3. Update the canonical IMPL-01 file list.
4. Regenerate the canonical IMPL-01 checksum manifest.

## Non-changes

No Python, YAML contract, source-normalization, reconciliation, test, CAL, TEST, holdout, F3, or G2 behavior is changed.

The accepted PRE-COMMIT functional evidence remains:

```text
focused tests = 30/30 PASS
full regression = 572/572 PASS
ruff = PASS
Bezirk = 12
cells = 1584
changed cells = 56
Stage1 = 161
Stage2 = 272
Stage3 = 478
max adjustment = 12
published-zero violations = 0
```

Official execution remains forbidden until this remediation is committed, pushed, and MAIN verifies `HEAD == origin/main` with a clean worktree.
