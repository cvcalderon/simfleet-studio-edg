# F1-P_CONSTR-IMPL-01 — PRE-COMMIT Remediation R1

**Trigger:** authoritative Linux PRE-COMMIT evidence.

## Observed

- focused tests: 29/29 PASS
- full regression: 571/571 PASS
- Ruff: one `I001` import-format issue in the verifier
- verifier: interrupted during stage 4 because the exact per-cell lexicographic tie-break performs 132 additional MILP solves per Bezirk (1,584 stage-4 solves over Berlin).

No commit, CAL, TEST, or G1 holdout read occurred.

## Remediation

1. Fix Ruff import formatting.
2. Preserve stages 1–3 exactly.
3. Replace only stage 4 with `CANONICAL_WEIGHTED_LINEAR_V1`: a single deterministic weighted MILP in canonical cell order after stages 1–3 are locked.
4. Update the non-decision-driving changed-cell regression anchor from 54 to 56.
5. Preserve decision-driving anchors: stage1=161, stage2=272, stage3=478, max adjustment=12, zero violations=0, 12/12 Bezirke feasible.
6. Add a unit test requiring exactly four MILP solves per Bezirk.
7. Report verifier reconciliation elapsed seconds for observability; no machine-specific hard timing threshold is introduced.

## Scientific impact

None on source data, hard constraints, or the first three optimization priorities. Stage 4 is a deterministic tie-break only. This amendment is made before first commit and therefore supersedes the PRE-COMMIT-only stage-4 implementation without reopening any frozen F3/G2 result.
