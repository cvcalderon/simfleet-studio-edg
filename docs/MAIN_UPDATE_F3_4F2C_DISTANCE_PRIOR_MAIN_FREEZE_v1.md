# MAIN update — F3.4f-2c Distance Prior MAIN Freeze

After successful F3.4f-2c verification and commit:

- `DG_DISTANCE_PRIOR / DIST_REF_REFERENCE = MAIN_FROZEN`;
- Distance Prior is authorized for D_GEN runtime use;
- selection source is the preserved A1 real-CAL RunBundle;
- `DIST_A_DA1` improves M2-DIST-01 by ~0.422660 km but fails the frozen P95
  guardrail (+1.852904 km > 0.50 km);
- all `DIST_B` candidates fail thresholded quantile guardrails;
- no challenger reaches bootstrap/promotion, so the reference remains incumbent;
- propagated runtime hard guardrail passes with 0 violations across 36,449
  generated distance rows;
- fitted artifact identity and TRAIN hashes remain unchanged;
- upstream artifacts remain `PA1 + COUNT_REF + CHA2 + TIME_B_TB2`;
- all five D_GEN component selections are now MAIN_FROZEN;
- Joint selected-vs-all-reference CAL gate remains NOT_AUTHORIZED;
- TEST remains SEALED;
- formal G2 remains NOT_EVALUATED.

Next methodological step: design/freeze the Joint selected-vs-all-reference CAL
gate before any execution or TEST opening.
