# F1-P_CONSTR-CAL-01 — materiality threshold rule v1

The purpose of this rule is to avoid choosing arbitrary numeric preservation tolerances before observing CAL while also preventing post-CAL threshold tuning.

For preservation family `j`:

```text
E0_j = error(P_TRS_V1_FINAL, CAL)_j

CAL_b = whole-household bootstrap replicate b
E0_j^b = error(P_TRS_V1_FINAL, CAL_b)_j

tau_j = percentile_95_higher( abs(E0_j^b - E0_j) )
```

with exactly 1000 bootstrap replicates and seed schedule frozen in the CAL-01 config.

Interpretation: `tau_j` is the upper 95% empirical sampling-uncertainty envelope of the baseline preservation error under household-atomic perturbation of CAL. A candidate difference smaller than or equal to this tolerance is not treated as material degradation.

This rule is frozen **before** CAL access. The numerical values are frozen **after** the single authorized CAL execution and before `1000A-1035` is opened.
