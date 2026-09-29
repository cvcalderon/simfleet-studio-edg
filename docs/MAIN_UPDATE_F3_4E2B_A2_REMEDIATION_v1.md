# MAIN update — F3.4e-2b A2 remediation

A2 progressed past CAL materialization and candidate-artifact validation but TIME_REF exhausted its finite 100-attempt rejection sampler on late-day states. Deterministic reconstruction confirms feasible support exists; the failure is a finite-sampler artifact rather than acceptance of an invalid temporal row.

Remediation: TIME_REF uses exact feasible-support conditional sampling in both isolated and propagated evaluation. Frozen support/probabilities, CRN seed schedule, hard temporal validator, candidate universe, CAL scope, sealed TEST, and G2 state remain unchanged.

After commit, A2 must not be reused because it is commit-bound. Issue A3 against the remediation commit and use a fresh RunBundle path.
