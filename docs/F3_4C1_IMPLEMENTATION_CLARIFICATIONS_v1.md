# F3.4c-1 implementation clarifications

These clarifications resolve implementation ambiguity without changing the frozen
scientific protocol.

1. Candidate promotion uses ISOLATED primary CRPS.
2. ISOLATED empirical participation is evaluation-only teacher forcing.
3. Full-day Trip Count guardrails include K=0 for empirical NoTrip days.
4. M2-COND-02 uses age, sex, primary activity, and household-size class; source_n<30
   is LOW_N/report-only.
5. PROPAGATED uses MAIN-frozen PA1 participation draws.
6. PA1 draws are candidate-independent within replicate; Trip Count draws use the
   `DG_TRIP_COUNT` namespace and CRN across Trip Count candidates.
7. PROPAGATED does not invent a new CRPS target on generated-mobile rows.
8. A propagated failure blocks MAIN freeze; it does not silently select another grid.
9. No Trip Count CAL rows are opened in F3.4c-1.
10. TEST remains sealed.
