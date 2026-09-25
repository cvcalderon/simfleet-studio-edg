# MAIN update — R6 fix v2

- R6 attempt01 is preserved as FAIL.
- Failure is isolated to within-tier stochastic donor identity; tiers and semantics were correct.
- Historical D_MATCH person-day/trip artifacts were recovered and exact individual hashes are now known.
- A compact 100k-row assignment witness was derived from the recovered historical person-days.
- Retry01 will recompute all deterministic semantics and M2 materialization from R4/R5/F0 inputs while replaying only the historical donor identity.
- Original RNG implementation remains explicitly NOT PRESERVED.
- R7 remains blocked until retry01 closes R6.
