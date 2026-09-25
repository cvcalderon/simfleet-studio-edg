# R3 implementation note v1 — P_TRS_EXP_V1 S-scale reproduction

## Scope

R3 reproduces the frozen PRE-F3 `P_TRS_EXP_V1` S-scale population. It is a reproduction step, not a new population-model design and not a G1 closure.

Frozen anchors:

- population: `P_TRS_EXP_V1`;
- scale: `S`;
- target persons: 10,000;
- expected generated households: 5,663;
- expected resource/access relations: 64,263;
- donor pool: 1,219 strict TRAIN households from the accepted R2 SplitManifest;
- sampling: whole household, replacement, probability proportional to `H_GEW`;
- generation seed: `20260922`;
- zone seed: `20260923`;
- historical structural validation: 23/23 PASS;
- historical snapshot SHA-256: `f37ffeda502929bdda4c16f0c30d297fd6c2743b4c1e50e987471c6e714f9d01`.

## Implementation

Core generation is implemented in `src/simfleet_edg/common/population_materializer.py`. The executable reproduction entry point is `src/simfleet_edg/repro/r3_ptrs_s.py`.

The implementation regenerates the three large population tables from source bytes and R2 rather than shipping historical large artifacts in the repository. It additionally recreates the compact F1.3a manifest, donor-reuse audit, zone-allocation audit, preservation audit and the frozen 23-check validation table.

`Notebook != CoreImplementation`: `notebooks/03_ptrs_s_reproduction.ipynb` only inspects RunBundle outputs.

## Determinism contract

The household draw sequence is deterministic in the same environment:

`numpy.random.default_rng(20260922)` + frozen donor order + normalized `H_GEW`.

The final residual household is sampled from donors whose `H_GR` exactly matches the remaining target, preserving household atomicity and exactly 10,000 persons.

Zone allocation uses the frozen F1.2a PLR private-household target artifact, largest-remainder integer quotas, and `numpy.random.default_rng(20260923)` to shuffle the repeated quota vector.

The historical snapshot digest is reproduced as SHA-256 of the concatenated SHA-256 strings of household, person and resource CSVs in that order.

## Source/contract boundaries

- `Haushalte` remains authoritative for roster membership, R_min, activity, household weights and household resources.
- `Personen` is enrichment only when `(H_ID, roster slot)` resolves.
- Roster-only persons receive no fabricated licence/access/membership enrichment.
- Household stock, personal access and time-dependent availability remain distinct.
- No trip, purpose, time, mode-choice, feasible-journey or execution outcome field enters M1.
- CALIBRATION and TEST households are not donor inputs.

## Known baseline geography note

`R3-BASELINE-GEO-001` is intentionally preserved rather than repaired during reproduction. Historical F1.3a prose/manifest lists both Pankower Tor (`03400831`) and Landweg (`06200418`) as no-stat-target exclusions. The frozen F1.2a PLR audit used operationally by the historical allocation has Pankower Tor unavailable but Landweg available with a zero private-household target. R3 follows the frozen operational artifact so that PRE-F3 reproduction does not silently alter prior evidence. This note is non-blocking for reproduction and remains for later MAIN review.

## RunBundle

The official run writes primary regenerated data, compact audits, input hashes, two validation layers, issue register, configuration snapshot, performance, manifest, log and checksums. A failed official run must be preserved and investigated rather than overwritten.
