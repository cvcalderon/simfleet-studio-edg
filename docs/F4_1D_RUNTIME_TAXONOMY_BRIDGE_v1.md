# F4.1d M2→M3 runtime taxonomy projection (MAIN-authorized V1)

The selected CHA2 model is frozen and can generate `PRIVATE_ERRAND`; this is valid M2 content.
M3 accepts only `HOME`, `WORK`, `BUSINESS`, `EDUCATION`, `ESCORT`, `LEISURE`, `OTHER`, `SHOPPING`.
After all five selected D_GEN components finish, and **before** the protected F4.1b M3 adapter,
apply **only** `PRIVATE_ERRAND → OTHER` to every trip origin and destination and daily final activity.
Any other out-of-vocabulary value raises a hard error. `OTHER` remains `OTHER`.

The transformation is a **lossy interface coarsening**, **not** evidence that private errands
are empirically equivalent to OTHER. No refitting, seeds, input features, TIME/DIST conditioning,
CAL/TEST data, synthetic donor identities or spatial phase are changed.

`activity_taxonomy_projection_audit_v1.csv` holds deterministic raw and projected records:
one TRIP record per actual trip (`row_id`, `trip_index`, original/projected origin/destination),
and one DAY record per person-day (raw/projected `final_activity`, empty `trip_index`).
The audit stays outside the M3 behavioural input. It is checksum-protected and included in
both-run byte-exact reproducibility and the RunBundle verifier. No 100k execution is authorized.

The post-push authorized smoke must retain 512 M1 identities, 512 days and 1,590 trips,
with original-label evidence: 144 PRIVATE_ERRAND destinations, 132 origins,
12 final-day activities and 98 affected person-days. MAIN remains closure authority.
