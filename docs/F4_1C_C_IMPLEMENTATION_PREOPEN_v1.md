# SimFleet-EDG — F4.1c-C
## Implementation PREOPEN — v1

**Workflow:** `SIMFLEET_EDG_WORKFLOW_V2`  
**State:** `IMPLEMENTATION_PREOPEN`  
**Design authority:** `F4_1C_C_OPERATIONAL_SUPPLY_AND_RESIDENTIAL_ANCHOR_DESIGN_FREEZE_V2`  
**Required parent:** `0958a673f0527b5bc87c16cb041e620f085ead87`

## Entry gate

Before any edit on the real clone:

```text
branch      = main
HEAD        = 0958a673f0527b5bc87c16cb041e620f085ead87
origin/main = 0958a673f0527b5bc87c16cb041e620f085ead87
worktree    = clean
```

The supplied repository archive is only a byte-for-byte implementation baseline. It has no `.git` metadata and cannot replace the real-clone gate.

## Frozen baseline quality fingerprint

Captured on the exact parent in the project Python 3.12 environment before the C overlay:

```text
Python = 3.12.3
Ruff   = 0.16.8
mypy   = 1.20.2

Ruff baseline:
  4 × I001
  sha256 = e3f0be7113487367e632dd414a6d2b87b280b45459ea911f1f88dde65b6fa938

mypy baseline:
  171 errors in 70 files
  sha256 = 5a0d2e8d60278426f02a2d8baa23f6b67c8cc53242256a629758220306864e6c
```

C may not clean or change this historical debt. C-scoped Ruff/mypy must pass and repository-wide diagnostics must remain exactly differential-zero relative to this baseline.

### Frozen CSV contract EOL normalization

The repository-entry audit records that selected CSV contract hashes were captured from `csv.writer` CRLF bytes before Git applied the frozen `*.csv text eol=lf` checkout normalization. For those CSV contract checks only, the frozen hash remains authoritative and the precheck accepts the documented LF/CRLF byte-normalization equivalence. It does not normalize fields, ordering, quoting, whitespace or any scientific/content bytes.

## Frozen geography

```text
M1 BEZIRK = 12 administrative boroughs / full14 IDs
LOR BZR   = 143 Bezirksregionen / 6-digit IDs
LOR PLR   = 542 Planungsräume / 8-digit IDs
```

The M1 borough polygon is the union, in EPSG:25833, of frozen LOR-BZR geometries sharing the M1 two-digit district suffix/prefix. The exact M1 full14 `home_zone_id` remains the canonical HOME parent.

## Implementation modules

```text
src/simfleet_edg/spatial/lor_lookup.py
src/simfleet_edg/spatial/location_supply.py
src/simfleet_edg/spatial/residential_anchor.py
src/simfleet_edg/repro/f4_1c_c_materialize.py
```

Responsibilities are those frozen by Worker Packet v1 and Design Freeze v2. Existing canonical mobility dataclasses are imported and reused; `canonical/mobility.py` is protected and unchanged.

## Operational boundary

C materializes only:

1. operational non-home `LocationSupplyRecord` objects inside frozen LOR;
2. evidence sidecars, including array-valued potential duplicate diagnostic groups;
3. residential source fragments clipped to the 12 M1 borough unions;
4. one deterministic canonical `ResidentialAnchor` per accepted M1 household.

C does **not** perform non-home destination assignment. `S_NEAR`, `S_DIST`, `S_ATTR`, F4.2, G3 and MiD TEST remain closed. `attractiveness` and `capacity` remain `NULL`. Potential duplicates are never merged destructively. Network access is forbidden.

## Determinism

HOME candidate selection is keyed by:

```text
SHA256(F4_1C_C_RESIDENTIAL_ANCHOR_V1|household_id|full14_parent_bezirk_id|SELECT)
```

Candidates are CDF-ordered by `candidate_id`. Building anchors use point-on-surface on the clipped EPSG:25833 fragment. Only the frozen landuse fallback uses keyed SHA-256 rejection sampling.

Canonical outputs use deterministic UTF-8 CSV.GZ with LF newlines, canonical row order, minified JSON subfields and `gzip_mtime=0`.

## Canonical outputs

```text
location_supply_v1.csv.gz
location_supply_evidence_v1.csv.gz
residential_supply_candidates_v1.csv.gz
residential_anchors_v1.csv.gz
residential_anchor_evidence_v1.csv.gz
materialization_exclusions_v1.csv.gz
```

## Required implementation flow

```text
real-clone gate
→ baseline quality fingerprint
→ implementation
→ focused tests
→ Ruff differential
→ mypy differential
→ full regression
→ verifier
→ exact-scope audit
→ PRE-COMMIT
```

At `PRE-COMMIT`, stop. Commit and push are performed by the user from PyCharm.

Only after the exact implementation commit is pushed and `HEAD == origin/main`:

```text
post-push freeze
→ materialization C
→ second full reproducibility run
→ compare exact output SHA-256
→ RunBundle
→ return to MAIN
```

## Exact scope

The only authorized repository paths are those in `docs/F4_1C_C_OVERLAY_FILELIST_v1.txt`. Any additional changed path is a blocker.
