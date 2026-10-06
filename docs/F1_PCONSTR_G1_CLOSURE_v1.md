# F1-P_CONSTR — G1 MAIN closure v1

## Decision

`G1 = PASS / CLOSED` after the accepted official A1-R1 evaluation of the external
feature holdout `G1_FEATURE_HOLDOUT_SENIOR_STATUS_V1` (`1000A-1035`).

The accepted population candidate is:

`P_CONSTR_RMIN_V2_HD_U` at scale `M`.

## Authoritative evidence

- parent code commit: `1aafadd95120c7875aac26f6504a6feb2aa5717a`
- official RunBundle SHA256: `8f37fb95d964ebd7c60d2ddf3befff10297b9e163438ac75d2caad9417877ea3`
- runner SHA256: `38fae45001fbd7adc73217915d20d3d06dbd8487d1201a4addc057a3e5cb3ecc`
- M realization SHA256: `00b440d58b2c4f7f5484e8260a43f1fb9f2ce69c0b5d5c23a6272aa3b2afa505`
- 1000A-1035 outer ZIP SHA256: `8db0c1a37159363918f6e6b59edb75fc637397ac9e5abc793560f7d98fedbe49`
- 1000A-1035 inner ZIP SHA256: `d8ccf5fee4244375de98e4805cbab28af38531ec13501a0468ce3e36bc667a81`
- 1000A-1035_de.csv SHA256: `46b046f2963a7c26d7eb6c3811d66b4dce31ca594c70688f0331d0117c747dc2`
- external A1 authorization JSON SHA256: `fabb997fe36b422e924a947d92db26e65cb9483d14df8aed6bc8663c8348e0d0`

## Attempt lineage

- A1: `ABORTED_BEFORE_METRIC_EVALUATION`
- A1-R1: `MECHANICAL_GEOGRAPHY_KEY_REMEDIATION`
- A1-R1 changed only the wrapper geography key from artificial `1..12` to the
  already-authoritative full Bezirk codes `11000000000001..11000000000012`.
- No scientific component changed.

## Frozen G1 results

| Metric | Role | Value | Threshold | Decision |
|---|---|---:|---:|---|
| G1-HOLD-SEN-BERLIN-TVD | DECISION | 0.016653027760625543 | 0.0815667541845037 | PASS |
| G1-HOLD-SEN-BEZ-WTVD | DECISION | 0.0166531932467901 | 0.0815667541845037 | PASS |
| G1-HOLD-SEN-BEZ-MAX | REPORT_ONLY | 0.023564294609585007 | — | REPORT_ONLY |

G1 passes iff both decision metrics are independently `<= 0.0815667541845037`.

The threshold remains a pre-holdout practical transfer tolerance from the
already-frozen CAL materiality thresholds. It is **not** a confidence interval
for senior-status holdout error.

## Independent audit

The RunBundle was rechecked independently after execution:

- repository identity: PASS
- RunBundle SHA/integrity: PASS
- internal checksums: PASS
- independent metric recomputation: PASS
- runner identity: PASS
- validation table: PASS (0 failures)

Independent Decimal recomputation:

- Berlin TVD: `0.01665302776062551085207649073`
- Bezirk weighted TVD: `0.01665319324679009384317431699`
- Bezirk max TVD: `0.02356429460958504522177634548`
- official five-leaf person total: `3532089`

## State after closure commit

- `G1 = PASS_CLOSED`
- `G2 = PASS_CLOSED_DO_NOT_REOPEN`
- `HOLD_MREAL_001 = RESOLVED_FROZEN`
- `HOLD_THRESH_001 = RESOLVED_FROZEN`
- CAL remains closed.
- MiD TEST remains consumed by G2 and must not be reopened.
- 1000A-1035 is `ACQUIRED / READ / EVALUATED`.
- candidate selection, threshold tuning, and same-lineage tuning after holdout
  remain forbidden.
- PLR and F3 are not modified by this closure.

This closure is administrative/reproducibility freeze only; it does not alter
the accepted scientific result.
