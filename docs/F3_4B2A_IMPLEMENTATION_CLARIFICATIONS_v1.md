# F3.4b-2a — PRE-OPEN implementation clarifications v1

Status: `FROZEN_BEFORE_FIRST_CAL_ROW_READ`.

These items only resolve computational details left implicit by the already-frozen protocol.
They do not change candidates, features, margins, guardrail tolerances, split roles or TEST policy.

## C1 — M2-COND-01 scalar guardrail used for promotion

For every candidate and every one of the 32 paired CRN realizations:

1. compute weighted `P(TripDay)` error for each static subgroup cell in the four frozen dimensions;
2. exclude source cells with `n < 30` from promotion (retain them as report-only LOW_N evidence);
3. take the maximum absolute error across supported cells;
4. use the arithmetic mean of those 32 per-replicate maxima as the candidate scalar guardrail.

Candidate worsening versus the current lower-complexity incumbent must be `<= 0.02`.

## C2 — PART_B calibration share-error rule

The 5-fold household cross-fit sigmoid decision uses:

- log-loss gain from cross-fit predictive probabilities;
- trip-day-share error from **generated outcomes**, consistent with M2-PART-01 and the
  F3.4a stochastic point-estimation rule.

Specifically, uncalibrated and cross-fit calibrated probabilities are subjected to the same 32
common-random-number uniforms. For each version, compute the weighted trip-day-share absolute
error in each replicate and average across 32. Calibration may be retained only if worsening is
`<= 0.005` and cross-fit log-loss gain is `>= 0.002`.

Direct probability-share error is retained as report-only diagnostic evidence.

## C3 — Failed real-CAL run preservation

The official runner writes to `<output>.partial` and renames atomically only after a successful
RunBundle is complete and checksummed. If execution fails after CAL may have been opened, the
partial bundle is preserved with `failure.json`; it must never be silently deleted or retried under
the same run identity.
