# F3.3d — PRE-CAL Entry Gate Contract v1

## Purpose

F3.3d is the final gate between PRE-CAL implementation and the first controlled CAL read.

The gate itself **must not read CAL**.

## Required completed layers

- F3.3a PRE-CAL Core
- F3.3b Component CAL Adapters
- F3.3c PRE-CAL Execution Harness

## Gate checks

The repository verifier must establish all of the following before CAL is authorized:

1. exact F3.3a/b/c Git lineage;
2. committed overlay checksum manifests all validate against current repository bytes;
3. frozen F3.1c witness hashes remain exact;
4. candidate registry is exactly 31 TRAIN-only unselected artifacts;
5. all 31 artifact model/manifest bytes match the registry;
6. primary metrics, practical margins and guardrail tolerances match the PRE-CAL freeze;
7. ISOLATED and PROPAGATED evaluation modes are implemented;
8. 32 paired stochastic replicates and candidate-independent CRN are frozen;
9. 1000 paired whole-household bootstrap recomputations and 95% percentile CI are frozen;
10. PART_B five-household-fold calibration rule is implemented;
11. REF -> A -> B no-composite promotion logic is implemented;
12. selected-pipeline vs all-reference TEST gate exists and keeps formal G2 unevaluated;
13. CAL access was blocked throughout PRE-CAL;
14. TEST remains sealed;
15. CAL rows read = 0;
16. TEST rows read = 0;
17. candidate selection = NONE;
18. accepted PRE-CAL regression evidence exists:
    - F3.3a: 23 focused / 197 full;
    - F3.3b: 57 focused / 254 full;
    - F3.3c: 17 focused / 271 full.

## PASS semantics

A PASS authorizes only:

`the next controlled CAL evaluation run`

It does **not**:

- select any candidate by itself;
- authorize TEST;
- close formal G2;
- authorize post-CAL redesign.

## FAIL semantics

Any failed check keeps CAL blocked.
