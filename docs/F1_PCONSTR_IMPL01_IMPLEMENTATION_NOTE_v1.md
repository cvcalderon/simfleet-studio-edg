# F1-P_CONSTR-IMPL-01 — implementation note v1

Scope is intentionally narrow:

```text
source staging/normalization
+ age_zensus_11_v1 projection
+ EDG_RECONCILED_PHH_PERSON_CUBE_V1
+ PRE-COMMIT verifier
+ official reconciliation RunBundle runner
```

Not implemented here:

```text
scale projection
H6_COMPLETION_V1
P_TRS_V1_FINAL
HD_U / HD_W
PLR allocation
CAL
G1 feature holdout
any F3 change
```

The reconciler implements the frozen hierarchical contract. Stages 1–3 retain the exact lexicographic scientific priorities. Stage 4 uses `CANONICAL_WEIGHTED_LINEAR_V1`: one deterministic weighted linear MILP in canonical cell order after stages 1–3 are locked at their integer optima. This supersedes the PRE-COMMIT-only exact per-cell stage-4 implementation, which was operationally too slow on the authoritative Linux HiGHS build.

The expected implementation anchors are:

```text
12 Bezirke
1,584 detailed cells
56 changed detailed cells
stage1 = 161
stage2 = 272
stage3 = 478
max detailed adjustment = 12
```

These are regression anchors derived from the frozen source package; they are not additional observed evidence.
