# F3.4b-2c — MAIN Participation Selection Freeze

Required parent: `d3ad3ba5881cc5629db4b64782441199c6f69df8`.

Source evidence: the controlled real-CAL F3.4b-2b RunBundle for `DG_PARTICIPATION`.

## Frozen decision

`DG_PARTICIPATION::PART_A::PA1` is frozen as the selected Participation artifact.

This freeze follows the pre-registered lexicographic procedure:

- PART_A within-family winner: PA1.
- PART_B within-family winner: PB1.
- REF → PA1 promotion passes practical margin, bootstrap CI, and guardrails.
- PA1 → PB1 promotion fails practical margin and bootstrap CI criteria.
- PART_B calibration is not applicable because PART_B is not selected.
- TEST remains sealed.
- Formal G2 remains NOT_EVALUATED.
- This artifact does not authorize DG_TRIP_COUNT execution by itself.

## Key CAL evidence

- PA1 weighted Bernoulli log-loss: `0.3388982435885032`.
- PART_REF weighted Bernoulli log-loss: `0.3537001757129491`.
- REF → PA1 point improvement: `0.014801932124445916`.
- Practical margin: `0.005`.
- Bootstrap 95% CI: `[0.00640925994764624, 0.024315528108916604]`.
- PA1 → PB1 point improvement: `-0.015440012062591768`.
- Bootstrap 95% CI: `[-0.05298765627518805, 0.013748073229916854]`.
- All relevant guardrails pass.
- CAL physical rows read: `929`.
- CAL evaluation rows: `460`.
- TEST rows read: `0`.
