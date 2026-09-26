# R7 local validation v1

Candidate overlay validation completed before delivery.

```text
R7 unit tests                         8/8 PASS
Reconstructed full suite            45/45 PASS
Python compile                        PASS
R7 prep verifier                     PASS
R7 official-like local run           PASS
Input hashes                         15/15 PASS
F2.2 validation                      18/18 PASS
Historical witnesses                 11/11 accepted
```

Historical reproduction:

```text
BYTE_EXACT                           10/11
NUMERIC_EQUIVALENT                    1/11
```

The numeric-equivalent artifact is
`simfleet_edg_F2_2_global_metrics_v1.csv`; maximum absolute numeric difference
was approximately `1.185718e-13`, below the frozen `atol=1e-12`.

Official-like local performance:

```text
wall_seconds       9.932749
cpu_seconds        9.923203
peak_rss_kib       685004
```

The local validation commit is not a project code identity and must not be used as
the official R7 commit. The official identity will be the commit produced on the
user VM after applying, testing and pushing this overlay.
