# F3.4f-1 — Distance Prior implementation clarifications

Status: `FROZEN_BEFORE_FIRST_DISTANCE_CAL_ROW_READ`.

These clarifications do not alter candidates, TRAIN fits, feature semantics, practical margin, frozen quantile tolerance, split roles or TEST policy.

1. Candidate selection uses ISOLATED `M2-DIST-01` weighted Wasserstein km.
2. ISOLATED uses all 1,147 raw-distance CAL rows; missing upstream context is preserved and routed through already-frozen missing/backoff behavior.
3. `source_trip_id` is technical identity only and cannot enter X.
4. P50/P90/P95 absolute-error worsening tolerance is 0.50 km each.
5. MEAN is computed and reported but is not thresholded because no numeric mean tolerance was preregistered.
6. M2-DIST-02 is report-only and never replaces the raw-distance primary target.
7. Distance Prior gets a dedicated real-CAL runner; generic `execute_candidate()` is not used directly.
8. ISOLATED RNG trip identity is `context_row_id + source_trip_id`; PROPAGATED identity is `context_row_id + generated_trip_index`; candidate identity is absent from the CRN key.
9. PROPAGATED uses MAIN-frozen `PA1 + COUNT_REF + CHA2 + TIME_B_TB2` and is hard-runtime-admissibility-only.
10. No generated-trip W_GEW mapping is introduced in F3.4f; that semantic must be frozen separately before the joint selected-vs-reference CAL gate.
11. A propagated hard failure blocks MAIN freeze; it does not silently select another candidate.
12. No Distance CAL row is read in F3.4f-1. TEST remains sealed.
