# MAIN update — R3 preparation v1

## Status

`R0 = SUPERADO`  
`R1 = SUPERADO`  
`R2 = SUPERADO`  
`R3 = IMPLEMENTATION PREPARED / VM QUALITY GATE PENDING`

## R3 objective

Reproduce the frozen PRE-F3 `P_TRS_EXP_V1` S=10k population before any R4/F3 activity.

Expected exact anchors:

```text
persons             10,000
households           5,663
resources           64,263
linked Personen      8,987
roster-only          1,013
strict TRAIN pool    1,219
unique donors used   1,125
max donor reuse         25
median used reuse       4.0
structural checks    23/23 PASS
snapshot SHA256      f37ffeda502929bdda4c16f0c30d297fd6c2743b4c1e50e987471c6e714f9d01
```

Seeds remain `20260922` for household generation and `20260923` for PLR assignment.

## Scientific status

The result remains `PRE-G1 EXPERIMENTAL RESULTS`. R3 does not close G1 and does not authorize F3.1. The objective is reproduction of the existing baseline, not improvement.

## Baseline note

`R3-BASELINE-GEO-001` records the pre-existing Landweg/Pankower-Tor wording-vs-operational-artifact discrepancy. No frozen operational input is silently changed in R3.

## Next action

Run VM quality gates (`pytest`, Ruff, `verify_r3_prep.py`), commit/push on clean `main`, then execute the official `R3_ptrs_s_v1` RunBundle exactly once.
