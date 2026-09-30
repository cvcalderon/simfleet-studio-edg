# F3.4f-1 — Protocol gap resolution

## G1 — Mean-distance guardrail has no frozen tolerance

Evidence already frozen before Distance CAL:

- F3.1c lists `raw-distance mean`, `p50`, `p90`, `p95` and M2-DIST-02 as Distance summary/guardrail evidence.
- F3.1c/F3.3/F3.4a freeze `distance_quantile_absolute_error_worsening_km = 0.50`.
- The tolerance is explicitly named and documented for quantiles (`p50/p90/p95`).
- F3.4a forbids changing a guardrail tolerance during CAL.
- The joint-gate preregistration forbids a new threshold after CAL inspection.

### Resolution

Do **not** invent a mean threshold now.

`MEAN` remains mandatory report-only evidence. P50/P90/P95 remain the thresholded Distance summary guardrails at 0.50 km. This preserves the originally frozen numeric decision rules and avoids a post-hoc decision criterion.

This resolution is an interpretation of an incomplete preregistration, not a new scientific threshold.

## G2 — PROPAGATED Distance distribution weighting is underspecified

The selected upstream pipeline can generate a different number of trips than observed CAL. Source primary Distance evidence is weighted by trip-level `W_GEW`, but no preregistered rule maps those source trip weights to an arbitrary number of propagated generated trips.

### Resolution for component CAL

Do not invent a generated-trip weighting rule during F3.4f.

Use PROPAGATED only as hard runtime-admissibility after provisional ISOLATED selection. Candidate selection and numeric Distance distribution guardrails remain ISOLATED.

A full-pipeline generated-trip weighting convention is a separate prerequisite that must be frozen before the later selected-vs-all-reference joint CAL gate. It must not be inferred from Distance component results.
