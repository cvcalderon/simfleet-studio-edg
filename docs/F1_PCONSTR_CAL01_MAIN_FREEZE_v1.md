# F1-P_CONSTR-CAL-01 A1 — MAIN Freeze PREOPEN

**Proposed status after commit:** `CAL01_A1_CLOSED_FROZEN`
**Runner commit:** `c8c4e1b3e479bff3ec9351998d2d880c3ec00c50`
**Official CAL RunBundle SHA256:** `672ef2032ff80080e8b03a59b11f34505556b76a53177bdbe28ed508fe61b839`
**Selected candidate:** `P_CONSTR_RMIN_V2_HD_U`

## MAIN audit decision

`F1-P_CONSTR-CAL-01 A1 = ACCEPTED FOR MAIN FREEZE`

The official RunBundle is internally checksum-consistent, reports `PASS`, contains no issues,
materializes zero MiD TEST rows, and leaves `1000A-1035`, PLR and F3 untouched.

## CAL reference

The frozen runner PREOPEN selected `PRIVATE_HOUSEHOLDS` as the preservation reference **before**
CAL execution:

- split CAL households, all: **268**
- strict R_min CAL households: **263**
- private CAL households materialized: **267**
- private CAL person rows materialized: **470**

The 263 strict households are the fit-eligible R_min subset; the 267 private households are the
preservation reference. This distinction is not a post-CAL change.

## `g1_thresholds_v1`

| Family | Frozen tau |
|---|---:|
| `ACTIVITY_BY_AGE` | `0.07293353416541049` |
| `LICENSE_BY_AGE_SEX` | `0.0815667541845037` |
| `HH_CAR_STOCK_BY_SIZE` | `0.0660999637102583` |
| `HH_BIKE_EBIKE_STOCK_BY_SIZE` | `0.07409481595332659` |

Derivation remains exactly: whole-household bootstrap, 1000 replicates, Q95 `higher`,
master seed `20261005`, substream `F1_PCONSTR_CAL_MATERIALITY_V1`.

## Independent selection audit

### Stage 1 — HD_U vs HD_W

HD_W produces no preservation-family improvement greater than the corresponding frozen `tau`.
Therefore the preregistered inconclusive/tie rule retains the simpler incumbent:

`P_CONSTR_RMIN_V2_HD_U`.

### Stage 2 — constrained winner vs P_TRS

- fit L1: **350 < 3968**
- max absolute fit error: **4 <= 29**
- material preservation degradations vs P_TRS: **0 / 4**
- engineering/integrity gate: **PASS**

Therefore MAIN freezes:

`selected_candidate = P_CONSTR_RMIN_V2_HD_U`

## Boundary after freeze

- CAL: consumed for candidate selection and threshold derivation; **must not be reused as independent validation**.
- MiD TEST: `DO NOT REOPEN`; G2 remains closed.
- `1000A-1035`: **UNREAD and NOT YET AUTHORIZED**.
- PLR: not performed.
- F3: untouched.
- G1: OPEN.
- G2: PASS / CLOSED / DO NOT REOPEN.

A separate PREOPEN + authorization step is required before reading `1000A-1035`.
