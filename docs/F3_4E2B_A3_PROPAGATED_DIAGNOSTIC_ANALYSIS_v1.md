# F3.4e-2b — A3 propagated diagnostic analysis

A3 produced a valid controlled real-CAL RunBundle but selection was blocked by the propagated temporal guardrail.

D1 isolated the propagated failures without authorizing selection or downstream CAL.

Frozen diagnostic anchors:

- CAL physical rows: 1712
- fixed source cohort: 378 person-days
- active person-day replicates per artifact: 10680
- TIME_REF failures: 1097, all `NO_FEASIBLE_SUPPORT`
- TIME_B_TB1 failures: 414, all `FINITE_REJECTION_EXHAUSTION`
- shared failed context-replicates: 359
- TIME_REF-only failures: 738
- TB1-only failures: 55
- candidate selection remains `NONE`
- TEST remains sealed
- Distance Prior real CAL remains unauthorized
- formal G2 remains `NOT_EVALUATED`

## Interpretation

The two artifact failures have different semantics. TIME_REF reaches states for which its frozen empirical support contains no temporally feasible point. TIME_B_TB1, by contrast, has feasible model mass but can exhaust the arbitrary 100-attempt rejection cap. D1 therefore supports a technical remediation of the TIME_B sampling mechanism before any scientific decision about the remaining propagated reference infeasibility.

## Remediation

TIME_B real-CAL evaluation replaces finite rejection with exact conditional sampling under the frozen temporal state:

1. reconstruct the frozen quantile-based departure and duration distributions after half-up rounding;
2. retain their original probability mass;
3. condition the independent joint distribution on the same frozen temporal invariant;
4. sample using the existing candidate-independent CRN seed;
5. fail hard only when the feasible probability mass is genuinely zero.

This does not repair generated values, alter quantile predictions, change candidates or grids, modify the metric/margin/bootstrap protocol, read TEST, or authorize downstream CAL.
