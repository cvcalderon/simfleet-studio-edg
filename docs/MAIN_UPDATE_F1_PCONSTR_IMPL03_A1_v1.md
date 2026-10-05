# MAIN UPDATE — F1-P_CONSTR-IMPL-03 A1

## Decision

`F1-P_CONSTR-IMPL-03 A1 = ACCEPTED FOR MAIN FREEZE`

## Authoritative lineage

- IMPL-02 freeze commit: `2f547ec53501245af1d605a866e19febfc5089b8`
- IMPL-03 implementation commit: `9feb3471b8c1581b18571cbdc0b9e27001e3f632`
- Official IMPL-03 RunBundle SHA256: `78c2a939cd7de08b048aed0cbd2a21abed73c87b68ce71860af1bbe321dd42a6`

## Frozen outputs

- TRAIN catalog: 1,219 strict households, 8 six-plus templates, 2,244 private person donors, 249 equivalence classes, 22/22 age×sex support cells.
- S fully materialized for P_TRS, HD_U and HD_W.
- P_TRS S: 5,309 HH, 10,000 persons, fit L1=3,968, max error=29.
- HD_U S: 5,485 HH, 10,000 persons, fit L1=350, max error=4.
- HD_W S: 5,485 HH, 10,000 persons, fit L1=350, max error=4.
- Shared 6+ blueprint across all variants: 80 households / 685 persons.
- M remains plan-only: 54,026 households, 93,127 persons, fit L1=3,172, max error=40.

## Interpretation

No winner has been selected. The S fit anchors establish implementation correctness only. HD_U vs HD_W and P_TRS vs P_CONSTR remain candidates for later CAL evaluation.

## Gates and boundaries

- G1 = OPEN.
- G2 = PASS / CLOSED / DO NOT REOPEN.
- CAL = UNREAD.
- MiD TEST not read by IMPL-03; globally consumed by G2.
- 1000A-1035 = UNREAD.
- PLR = NOT PERFORMED.
- G1 thresholds = NOT TUNED.
- F3 = UNTOUCHED.

## Next authorized design step after freeze commit

`F1-P_CONSTR-CAL-PREOPEN`, with CAL still sealed until formal authorization.
