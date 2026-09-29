# F3.4e-2b — A5 propagated lookahead remediation

## Status and evidence basis

This remediation is bound to parent commit `0ab96825486ca8111af95eb7d7594ea16c048d96` and follows the preserved A5 real-CAL RunBundle plus diagnostics D2–D7.

Frozen A5 isolated evidence is not redefined: `TIME_B_TB2` is the within-family B winner and is promoted over `TIME_REF_REFERENCE` by the frozen M2-TIME-01 rules. The remaining blocker is propagated temporal feasibility.

Diagnostic anchors:

- D2: `TIME_B_TB2` propagated failures = 182, all `NO_JOINT_SUPPORT_BEFORE_DAY_END`.
- D4: global one-minute minimum-slack conditioning reduces `TIME_B_TB2` propagated failures from 182 to 0.
- D5: the same universal minimum-slack policy does not solve the empirical reference (`TIME_REF_REFERENCE`: 1097 -> 1069).
- D6 lexical audit reported no documentary reference hard requirement, but direct contract review supersedes that lexical false negative: the frozen PREOPEN contract explicitly requires both reference and provisional incumbent to preserve zero propagated temporal invariant violations. The conjunctive gate therefore remains unchanged.
- D7: exact full-chain conditioning over the already-frozen empirical joint support reduces `TIME_REF_REFERENCE` propagated failures from 1097 to 0. The frozen support contains complete paths for every generated K through 50; no support row or probability is added.

## Authorized implementation change

Only propagated sampling changes.

### TIME_B

For a current trip with `q > 0` future trips, exact sampling from the frozen reconstructed departure/duration distribution is conditioned on

`current_arrival_absolute_minute <= 1440 - q`.

This reserves only the universal frozen minimum duration of one minute per future trip. It is an exact conditional draw from the existing TIME_B law; no generated value is repaired or invented.

Sampling policy identifier:

`EXACT_TIME_B_FULL_CHAIN_MIN_SLACK_CONDITIONAL_V1`

### TIME_REF

Before propagated replay, exact dynamic thresholds are computed from `joint_temporal_support`. A support row is eligible only if the current row passes the frozen validator and its arrival still admits at least one complete path for every remaining trip through the same frozen empirical support.

The original support probabilities are retained and renormalized only over the exact full-chain feasible subset at the current state. No support row is added, altered, imputed, or repaired.

Sampling policy identifier:

`EXACT_REFERENCE_FULL_CHAIN_SUPPORT_CONDITIONAL_V1`

## Explicit non-changes

- ISOLATED generation and all A5 isolated metrics remain on their existing samplers.
- Candidate universe remains 7 artifacts.
- `TIME_B_TB2` identity and fitted artifact are unchanged.
- `TIME_REF_REFERENCE` empirical joint support is unchanged.
- Candidate-independent RNG seed schedule is unchanged.
- Upstream `PA1`, `COUNT_REF`, and `CHA2` remain frozen.
- The conjunctive propagated gate remains `reference hard pass AND provisional incumbent hard pass`.
- Distance Prior real CAL remains unauthorized.
- TEST remains sealed.
- G2 remains `NOT_EVALUATED`.
- No MAIN freeze is performed by this remediation.

## Expected next step

After local pre-commit validation, commit this remediation, synchronize `main`, and issue a fresh commit-bound A6 real-CAL authorization. A5 and all diagnostics remain immutable historical evidence.
