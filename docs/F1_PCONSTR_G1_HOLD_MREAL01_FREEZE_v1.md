# F1-P_CONSTR-G1 — HOLD-MREAL-001 A1 MAIN freeze v1

## Decision

MAIN accepts the official `M` realization of the already-frozen winner
`P_CONSTR_RMIN_V2_HD_U` for `HOLD-MREAL-001`.

After this freeze commit:

```text
HOLD-MREAL-001 = RESOLVED / FROZEN
HOLD-THRESH-001 = OPEN
G1 = OPEN
G2 = PASS / CLOSED / DO NOT REOPEN
```

## Bound execution

- runner commit: `57891354e314df7bb38cd5b3f9e020f762826c49`;
- external A1 authorization JSON SHA256: `baa10be37bf4735fe06d0cf25e0afdcf7a83f51b5352d6ea1305b7a651be0911`;
- official deterministic RunBundle ZIP SHA256: `00b440d58b2c4f7f5484e8260a43f1fb9f2ce69c0b5d5c23a6272aa3b2afa505`;
- RunBundle ZIP size: `10345871` bytes;
- candidate: `P_CONSTR_RMIN_V2_HD_U`;
- scale: `M`;
- candidate seed: `20261005`;
- H6 seed: `20261004`.

## Frozen realization anchors

The materialized population has exactly `100000` persons in `54828` households.
The 1..5 branch has `93127` persons in `54026` households, and the 6+ branch has
`6873` persons in `802` households. Target-fit anchors remain L1=`3172` and
max-absolute=`40`. TRAIN-only donor integrity holds with zero CAL and TEST donor
violations. The 6+ branch has min size `6`, max size `25`, and zero target
violations.

## Frozen core hashes

The seven core hashes are stored in
`F1_PCONSTR_G1_HOLD_MREAL01_CORE_HASHES_A1_SNAPSHOT_v1.json` and are verified
against the official RunBundle before this overlay may be committed.

## Absolute boundary

`1000A-1035` remains unacquired, unread and unauthorized. No holdout metric was
evaluated. CAL and MiD TEST remain closed, PLR allocation remains closed and F3
is untouched.

The next phase is threshold-only work for `HOLD-THRESH-001`. It must still use
TRAIN+CAL-only evidence and must complete before any `1000A-1035` acquisition.
