# F1-P_CONSTR-IMPL-03 A1 — MAIN Closure Freeze

**Status proposed after commit:** `IMPL03_A1_CLOSED_FROZEN`
**Implementation commit:** `9feb3471b8c1581b18571cbdc0b9e27001e3f632`
**Official RunBundle SHA256:** `78c2a939cd7de08b048aed0cbd2a21abed73c87b68ce71860af1bbe321dd42a6`

## Frozen scope

- TRAIN-only donor materialization.
- `P_TRS_V1_FINAL`.
- `P_CONSTR_RMIN_V2_HD_U`.
- `P_CONSTR_RMIN_V2_HD_W`.
- Shared `H6_COMPLETION_V1` donor/person blueprint across all three candidates.
- S fully materialized; M retained as constrained plan only.
- No candidate winner is selected in IMPL-03.

## Frozen TRAIN catalog

| Item | Value |
|---|---:|
| Strict TRAIN households | 1,219 |
| TRAIN 6+ templates | 8 |
| TRAIN private person donors | 2,244 |
| Equivalence classes | 249 |
| Age×sex donor support cells | 22/22 |

## Frozen S anchors

| Candidate | Households | Persons | Resources | Fit L1 | Max error |
|---|---:|---:|---:|---:|---:|
| `P_TRS_V1_FINAL` | 5,309 | 10,000 | 62,745 | 3,968 | 29 |
| `P_CONSTR_RMIN_V2_HD_U` | 5,485 | 10,000 | 64,313 | 350 | 4 |
| `P_CONSTR_RMIN_V2_HD_W` | 5,485 | 10,000 | 64,173 | 350 | 4 |

All candidates have 0 CAL donor violations, 0 TEST donor violations, and 0 six-plus target violations.

## Shared 6+ branch

All three variants materialize exactly 80 6+ households and 685 persons in S using the same frozen blueprint. The official in-memory signature recorded by the RunBundle is:

`3a65324381175ac80984553ff5337e90c9a9efad787014191852b39bf8787c6a`

The equality of the blueprint across variants is the frozen semantic contract. The exact in-memory signature is an execution artifact and is not a CSV round-trip serialization contract.

## Frozen M plan anchors

- Generated/target strict persons: **93,127 / 93,127**.
- Generated/target strict households: **54,026 / 54,026**.
- Catalog equivalence classes: **249**.
- Positive equivalence classes: **241**.
- Fit L1: **3,172**.
- Maximum cell error: **40**.
- Plan rows: **2,740**.

M is not fully materialized in IMPL-03 A1.

## Interpretation guardrail

The lower fit error of HD_U/HD_W relative to P_TRS is an implementation anchor, not a candidate-selection decision. IMPL-03 does **not** choose P_CONSTR over P_TRS and does **not** choose HD_U over HD_W. Candidate selection belongs to later CAL under a separately frozen evaluator and threshold rule.

## Boundaries

- CAL: unread.
- MiD TEST: not read by IMPL-03; globally consumed by G2 and MUST NOT be reopened.
- 1000A-1035: unread.
- Candidate selection: deferred.
- G1 threshold tuning: not performed.
- PLR allocation: not performed.
- F3: untouched.
- G1: OPEN.
- G2: PASS / CLOSED / DO NOT REOPEN.

## Next step after freeze commit

`F1-P_CONSTR-CAL-PREOPEN` may be designed, but CAL remains unread until its formal authorization package is frozen and approved.
