# MAIN update — R4 preparation

## Status

`R4 — P_TRS_EXP_V1_M reproduction`: IMPLEMENTATION READY / OFFICIAL RUN NOT STARTED.

## Frozen anchors

```text
persons                  100000
households                56365
resource_relations       639661
linked_persons            89459
roster_only_persons       10541
unique_donors_used         1213
max_donor_replicas          203
median_replicas_used        39.0
historical_validation     23/23 PASS
snapshot_sha256           a3a9be46286d150e1032d1872ca0e47775407ee14835980f0d5a71be92c57f7d
```

## Reproduction policy

Primary snapshot bytes and the compact core witnesses are EXACT. Preservation
and S→M stability metrics are NUMERIC_TOLERANCE (`1e-12`). Performance is
REPORT_ONLY / environment-dependent.

## Implementation delta

The common population materializer gains historical M identifier widths while
preserving S widths. The R3 HP_ID provenance correction is retained unchanged.
No scientific generation rule changes.

## Gate state

```text
R0  SUPERADO
R1  SUPERADO
R2  SUPERADO
R3  SUPERADO
R4  CURRENT
G1  OPEN
G2  NOT CLOSED
```
