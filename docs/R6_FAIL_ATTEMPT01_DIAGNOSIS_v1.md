# R6 FAIL attempt01 — diagnosis

## Status

`R6_d_match_v1 = FAIL / PRESERVED`

Commit: `23ab0a28723161ecf7cc164997ead187d16e9a19`

The first official R6 attempt reproduced all frozen matching-tier counts exactly, kept self-match and global fallback at zero, and passed the combined F2.1 structural validation 20/20. It did not reproduce the historical stochastic realization inside those tiers.

Observed attempt01:

- person-days: 100,000
- zero-trip: 15,392
- mobile: 84,608
- trip intents: 291,504
- R6 checks: 17/18
- F2.1 checks: 20/20
- bridge SHA-256: `6de94f58b19b1cd6f7c0b5aae175e7d444912dfcc571efcef412a757e2847367`

Historical anchors:

- zero-trip: 15,574
- mobile: 84,426
- trip intents: 291,508
- bridge SHA-256: `2711e5542302f4c1b3b28ee8dab8b19bc044f0c61a143645e165aa32f5d437b5`

## Root cause

The F2.1 artifacts preserved the matching hierarchy, `P_GEW` weighting, seed `20260924`, self-match prohibition and all semantic constraints, but did not preserve the exact RNG API/candidate-order implementation used to materialize the historical stochastic draw.

The historical D_MATCH person-day and trip files were subsequently recovered from the ChatGPT Library. Their exact hashes are:

- person-days: `d908ce562f2d14de017d369aab61f3d96e998b4f19f1d8753c1820c2c799a65e`
- trips: `7d3617811aef04ca6e83c15e2bc64643e2fe6a7a922bd51103fc9ca7073606b6`

These hashes reconstruct the frozen historical bridge hash exactly when combined with the accepted R5 hashes.

## Controlled correction

Retry01 does not guess or tune a replacement RNG implementation. It uses a compact historical assignment witness containing only:

`generated_person_id -> diary_source_hp_id`

All tier membership, self-match constraints, donor completeness, TRAIN eligibility, M2 fields and trip materialization are recomputed from frozen R4/R5/F0 inputs. The witness replays only the historical stochastic donor identity.

This is an exact historical reproduction mechanism, not a claim that the original RNG implementation has been recovered.
