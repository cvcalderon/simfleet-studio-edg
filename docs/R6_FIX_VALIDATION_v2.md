# R6 fix v2 — preparation validation

Preparation checks performed before delivery:

- R6-specific unit suite: 7/7 PASS
- reconstructed repository suite: 37/37 PASS
- Python compilation: PASS
- assignment witness rows: 100,000
- assignment witness SHA-256: `55a0a37fd9fea048f4b8e1f8c042a10d09b0b5cf5c749e34fca3d61f77268494`
- independently reconstructed historical D_MATCH person-days SHA-256: `d908ce562f2d14de017d369aab61f3d96e998b4f19f1d8753c1820c2c799a65e`
- independently reconstructed historical D_MATCH trips SHA-256: `7d3617811aef04ca6e83c15e2bc64643e2fe6a7a922bd51103fc9ca7073606b6`
- derived combined bridge SHA-256: `2711e5542302f4c1b3b28ee8dab8b19bc044f0c61a143645e165aa32f5d437b5`

Ruff remains an execution-side quality gate on the official VM.
