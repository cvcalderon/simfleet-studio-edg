# F3.4f-2a — DG_DISTANCE_PRIOR Synthetic PRE-OPEN

## Status

`SYNTHETIC_PREOPEN_IMPLEMENTATION`, parent commit `6ef56286460939e57b4a01703f56b47967615bea`.

## Purpose

Validate the dedicated Distance Prior adapter/orchestration path against the five frozen TRAIN artifacts before any real Distance CAL file is opened. This phase emits synthetic smoke metrics only; it cannot select or promote a candidate.

## Frozen boundaries

- CAL rows read: `0`.
- CAL files read: `[]`.
- Candidate selection: `NONE`.
- Real Distance Prior CAL: `NOT_AUTHORIZED`.
- Joint CAL gate: `NOT_AUTHORIZED`.
- TEST rows read: `0`; TEST remains sealed.
- Formal G2: `NOT_EVALUATED`.

## Synthetic execution

Five frozen artifacts are hash-validated and loaded through `DistancePriorAdapter`. Thirty-two candidate-independent CRN seeds are used. Each candidate is sampled 32 times from an adapter-valid synthetic context, yielding 160 total generated draws.

The synthetic `M2-DIST-01` Wasserstein value is an implementation smoke result only and has no scientific candidate-selection role. MEAN, P50, P90 and P95 are also emitted only to validate summary plumbing. The real-CAL semantics frozen in F3.4f-1 remain unchanged: MEAN is report-only/unthresholded; the `0.50 km` tolerance belongs to P50/P90/P95.

## Required PASS evidence

- all five artifact hashes validate;
- 32 identical seed identities across all candidates;
- 160/160 generated distances are finite and strictly positive;
- 5 synthetic primary rows and 20 summary rows are produced;
- RunBundle checksums validate;
- no synthetic metric is decision-driving;
- no CAL or TEST file is read.

## Exit

A PASS permits commit of F3.4f-2a and design/implementation of the commit-bound F3.4f-2b real-CAL PREOPEN. It does **not** authorize real CAL execution.
