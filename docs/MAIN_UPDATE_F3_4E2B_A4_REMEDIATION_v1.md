# MAIN update — F3.4e-2b A4 remediation

A4 RunBundle passed integrity but TIME_B isolated scoring was blocked: TA/TB aside, all TIME_B grids showed exactly 1120 hard failures. This equals the 35 retained `__MISSING_CONTEXT__` CAL rows times 32 CRN replicates.

Root cause: the A3 exact TIME_B conditional sampler did not accept the frozen `trips_remaining_after_current=None` semantics established by A1. The remediation preserves missing K as unknown, applies future-trip feasibility only when K is known, and leaves all scientific selection rules unchanged.

Status before commit: candidate selection NONE; Distance Prior CAL unauthorized; TEST sealed; G2 NOT_EVALUATED.
