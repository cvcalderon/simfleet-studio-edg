# MAIN update — F3.4e-2b A3 propagated remediation

A3 real-CAL completed with a valid RunBundle. Isolated CAL promoted TIME_B_TB1 over TIME_REF, but selection remained blocked because the propagated temporal guardrail failed.

D1 classified every TB1 propagated failure as `FINITE_REJECTION_EXHAUSTION` (414/414), while every TIME_REF failure was `NO_FEASIBLE_SUPPORT` (1097/1097). The mechanisms are distinct.

Remediation is limited to TIME_B sampling in the real-CAL evaluation path: replace the finite 100-attempt rejection cap with exact conditioning of the frozen quantile-induced discrete distribution on the unchanged temporal invariant. Empty feasible support remains a hard failure. Candidate universe, frozen models, CRN seed schedule, upstream selections, CAL scope, TEST seal, Distance Prior authorization and G2 state remain unchanged.

After commit, A3 authorization must not be reused. Issue a fresh commit-bound A4 authorization and use a fresh RunBundle path.
