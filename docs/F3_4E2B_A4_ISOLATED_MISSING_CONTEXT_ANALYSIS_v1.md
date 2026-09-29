# F3.4e-2b A4 isolated missing-context analysis v1

A4 executed successfully as a controlled real-CAL RunBundle, but every TIME_B grid candidate failed the isolated hard temporal guardrail with exactly 1120 failures.

The count is diagnostic: F3.2a/F3.4e retain 35 CAL time rows whose `trip_position_class` is `__MISSING_CONTEXT__`; with 32 CRN replicates this is exactly `35 * 32 = 1120` failures per TIME_B candidate.

The A3 exact TIME_B sampler introduced a compatibility regression with the already-frozen A1 missing-context policy. `_trips_remaining_after_current(__MISSING_CONTEXT__)` deliberately returns `None` because source K is unavailable and must not be invented. The exact sampler accepted only an integer and evaluated `trips_remaining_after_current > 0`, causing an exception for all 35 missing-context rows in all 32 replicates.

## Remediation

- Change the exact TIME_B sampler contract to `int | None`.
- Apply the future-trip end-of-day restriction only when K is known and `trips_remaining_after_current > 0`.
- Preserve `None` when calling the frozen temporal validator.
- Do **not** coerce `None` to zero, because that would invent that the current trip is the final trip.
- Do not change candidate artifacts, quantiles, CAL scope, CRN schedule, primary metric, margin, bootstrap, upstream selections, Distance Prior authorization, TEST seal, or G2.

This is an implementation compatibility remediation only. A4 selection evidence remains blocked and no candidate is frozen.
