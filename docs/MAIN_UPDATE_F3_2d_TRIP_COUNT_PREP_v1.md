# MAIN update — F3.2d DG_TRIP_COUNT prep v1

F3.2c participation TRAIN fitting is closed/SUPERADO. F3.2d opens the TRAIN-only implementation lane for `DG_TRIP_COUNT`.

Frozen inputs: 1791 strict-TRAIN positive-count person-days; `K=1..50`; `Y=K-1`; `P_GEW` fit weight. Candidate slate: `COUNT_REF`, `COUNT_A/CA1..CA3`, `COUNT_B/CB1`. `COUNT_A` is NB2 with TRAIN-MLE dispersion and explicit truncated/renormalized `1..K_MAX_TRAIN` runtime support. `COUNT_B` implements literal `COUNT_BACKOFF_V1`, raw support threshold `source_n>=30`, and no smoothing.

This overlay trains nothing until implementation is committed. CAL fitting/scoring/selection remains disabled and TEST remains sealed. Formal G1 remains OPEN; formal G2 remains NOT_EVALUATED.
