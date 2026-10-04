# F1-P_CONSTR-IMPL-02 A1 — MAIN Closure Freeze

**Status proposed after commit:** `IMPL02_A1_CLOSED_FROZEN`<br>
**Implementation commit:** `b60017b8233856fa365bc63d4ddca9aa47e14566`<br>
**Official RunBundle SHA256:** `3a22dcf88dfbd83271d8b0b65d4d3c5590431bcf8ac269fddf713c4364474b81`

## Frozen scope

- Exact S/M/L person-domain scale projection from the reconciled IMPL-01 cube.
- Exact Bezirk totals.
- Preservation of structural zero cells.
- Exact divisibility for household-size classes 1..5.
- `H6_COMPLETION_V1`.
- `UNIFORM_WEAK_COMPOSITION_V1`.
- Donor materialization remains deferred to IMPL-03.

## Frozen anchors

| Scale | Persons | L1 numerator | P6 persons | H6 households | Min | Max | Size=6 | >10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| S | 10,000 | 1,392,907,648 | 685 | 80 | 6 | 16 | 19 | 18 |
| M | 100,000 | 1,360,353,392 | 6,873 | 802 | 6 | 25 | 230 | 150 |
| L | 1,000,000 | 1,326,140,012 | 68,711 | 8,024 | 6 | 38 | 2,389 | 1,537 |

Full-scale structural H6 target: **28,343 households**.

## Important semantic note

The reconciled IMPL-01 cube contains **242,676** persons in `6+`, while the published 1000A-1029 margin is **242,700**. This `-24` difference is expected: 1000A-1029 HSHGR2 is a Stage-2 margin objective under Cell-Key reconciliation, not a simultaneous exact hard equality. S/M/L projection therefore uses the reconciled cube and MUST NOT be “corrected” back to 242,700.

## Boundaries

- CAL: unread.
- MiD TEST: not read by IMPL-02; globally already consumed by G2 and MUST NOT be reopened.
- 1000A-1035: unread.
- Donor materialization: deferred to IMPL-03.
- PLR allocation: not performed.
- HD_U / HD_W candidates: not materialized.
- F3: untouched.
- G1: OPEN.
- G2: PASS / CLOSED / DO NOT REOPEN.
