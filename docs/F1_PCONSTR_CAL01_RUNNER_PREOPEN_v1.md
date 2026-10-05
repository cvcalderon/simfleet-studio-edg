# F1-P_CONSTR-CAL-01 — CAL runner PREOPEN v1

Required parent: `2313ef1689037bcb45812e896324585d8988b4bf`.

This overlay implements the controlled CAL runner but **does not authorize or execute it**.
The tracked protocol authorization is already positive and frozen. Actual CAL payload parsing
requires a second, external execution authorization bound to the exact runner commit after
this overlay is committed and synchronized.

## Ordering invariant

`execution authorization -> frozen non-CAL validation -> candidate RunBundle validation -> staging -> selective CAL materialization -> evaluation`

The negative tracked template must be rejected before candidate ZIP opening, CAL payload
parsing, or `.partial` staging creation.

## MiD combined-file caveat

The physical MiD household/person files combine TRAIN/CAL/TEST. The runner therefore scans
source lines only far enough to inspect the routing `H_ID`. Full CSV payload parsing and
DataFrame materialization occur only for authorized private CAL household IDs obtained from
the frozen SplitManifest. The RunBundle must state `test_rows_materialized = 0`; this is a
controlled materialization claim, not a claim that unrelated source-file bytes were never
traversed by the operating system.

## CAL output status

Thresholds and candidate selection emitted by this runner are **proposals awaiting MAIN
freeze**. They do not open 1000A-1035 and do not constitute final `g1_thresholds_v1`.
