# R2 — Eligibility + Household Split Reproduction — Implementation Note v1

## Purpose
Reproduce from the R1-verified MiD raw bytes, without fitting or population generation:

1. Berlin household scope (`BLAND=11`);
2. F0.2c household eligibility for `R_min`;
3. F1.1 deterministic household split;
4. descendant split inheritance for `Personen` and `Wege`;
5. strict age-band × sex support after splitting.

## Frozen rules
- Household is the atomic split unit.
- `Haushalte` roster defines membership and `R_min`.
- Private scope: `H_ART in {1,2}`; `H_ART=3` is diagnostic/out of core.
- Strict donor: `H_GR in 1..5` and all required roster sex/age fields valid.
- `H_GR=6` means `6_PLUS`, not exact six, and is not a strict donor.
- Split seed `20260912`.
- Hash `SHA256(seed|source_household_id)`.
- Strata: strict donors by household size 1..5, `PARTIAL_6_PLUS`, `PARTIAL_RMIN_MISSING`, `NON_PRIVATE`.
- Allocation inside each stratum uses largest remainder with tie-break `TRAIN > CALIBRATION > TEST`.
- Descendants inherit household split; `H_ID=0` remains `UNLINKED_EXCLUDED`.
- No mobility outcome is used to create the split.
- TEST remains sealed; this step only reproduces its assignment/counts.

## Exact witnesses
- Berlin households: `1770`.
- Private households: `1763`.
- Strict donors: `1742`.
- All split: `1238 / 268 / 264`.
- Strict split: `1219 / 263 / 260`.
- Frozen F1.1 split-manifest SHA-256: `5d0d4f2a41bc93b131de96d85192d8ff7002878e28e87515a0f88cedf1cebde8`.
- Descendants: Personen `2254 / 476 / 473 + 3 unlinked`; Wege `6692 / 1323 / 1349 + 6 unlinked`.
- Minimum strict age×sex support: TRAIN `23`, CALIBRATION `5`, TEST `6` over all 22 cells.

## Output contract
The official run writes a self-contained RunBundle with reproduced eligibility and split CSVs, input hashes, descendant counts, support cells, validations, performance, manifest, log and checksums. Raw MiD bytes are not copied into the bundle.
