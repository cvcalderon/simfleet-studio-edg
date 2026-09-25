# MAIN update — R6 preparation v1

## Status

R6 implementation package is ready for repository quality gates. Official 100k execution must occur in Proxmox/Jupyter from a clean synchronized `main` commit after accepted R5.

## Frozen R6 anchors

- matched person-days: 100,000
- zero-trip complete: 15,574
- mobile complete: 84,426
- trip intents: 291,508
- self diary matches: 0
- global fallback: 0
- seed: 20260924

Tier counts: 94,322 / 3,929 / 1,535 / 214 / 0 / 0.

Historical combined F2.1 bridge hash: `2711e5542302f4c1b3b28ee8dab8b19bc044f0c61a143645e165aa32f5d437b5`.

## Scope boundary

R6 closes only the D_MATCH / combined F2.1 reproduction evidence. R7 F2.2 diagnostics remain pending. F3 must not start before R7 closure and the consolidated PRE-F3 reproduction report.
