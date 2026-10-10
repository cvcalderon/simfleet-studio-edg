# SimFleet-EDG — F4.2b-B MAIN repository entry audit (2026-10-10)

**Status:** STATIC_ENTRY_PASS / REAL_CLONE_GATE_REQUIRED. **No scientific implementation or runtime executed here.**

## Input provenance and integrity

- Submitted Git archive: `F0-F4_2B_A-repo.zip` SHA-256 `1b82bda3a6bddfa4af5de4c610639b4e14e258510fbe15de20729a78c8bfca13`; **1,075 entries**; ZIP CRC valid. It contains **no `.git`**; it does NOT independently prove `HEAD=origin/main` nor ancestry. The only authorised real-clone baseline is reported `HEAD=1fdfd815fb5085cbc674b66baecd932a9bcabff9` on clean `main`.
- Frozen F4.2a RunBundle TAR SHA-256 `9d97b2294e24d97709bc8ba4f103f94b5b21d2c4d64d7ed72efe35d24f816247` — **matches MAIN closure**.
- Frozen F4.2b-A RunBundle TAR SHA-256 `7aa0c4756f2bfca3e58988c4053083f52d4b1166621ba29ae6629cf7edc6bb3b` — **matches MAIN exploratory closure**.
- F4.2a committed overlay: **21 byte-exact + 4 Git LF/CRLF canonicalisations**; F4.2b-A overlay: **17 byte-exact + 2 canonicalisations**. Each special case reconstructed the original frozen SHA from LF Git archive bytes using CRLF; not a tolerance or generic substitution. All 25 + 19 entries passed.
- Baseline SHA-256 captures **19 frozen implementation/source/test/config paths**; no previously committed path modifications are authorised. `pyproject.toml` unchanged.
- Proposed implementation scope: **25 new paths, 0 existing**. See `F4_2B_B_EXACT_25_NEW_PATH_SCOPE_v1.txt`.

## Independent read-only stable-anchor source coverage

From original F4.2a `dgen_A` M2 trips and frozen `S_DIST` stable anchor outputs plus original F4.2b-A `A` sidecar:

| Measure | Count |
|---|---:|
| Original person-days | 100,000 |
| Original trips | 325,613 |
| ESCORT days | 15,381 |
| Frozen CORE S_DIST person-purpose stable keys | 30,055 |
| Frozen sidecar person-purpose stable keys | 7,621 |
| WORK/EDUCATION person-purpose keys needed in ESCORT days | **7,621** |
| Needed keys exactly covered by existing sidecar | **7,621 / 7,621** |
| Needed keys absent from CORE + sidecar | **0** |
| CORE ↔ sidecar overlapping keys | **0** |

**Interpretation:** the needed stable person-purpose keys exist in the already frozen sidecar. This is a read-only key-membership verification, NOT a spatial realization, and does not prove that all 7,621 target locations pass all later full-day spatial gates. Do not silently create extra anchors.

## Source-code interface mapping

- `src/simfleet_edg/spatial/spatialize_core.py`: `Spatializer(indices, locations, anchors)`; `Spatializer._resolve(origin,p, purpose,'S_DIST')` uses the accepted CandidateIndex policy and deterministic tie rules; `Spatializer.metric(ref)` projects EPSG:4326 → EPSG:25833. For ESCORT days, **do not use** `Spatializer.spatialize()` because it excludes ESCORT plans by design. Call existing F4.2a `_resolve` for nonstable occurrence destinations only, without modifying it or copying policy code.
- `src/simfleet_edg/spatial/spatial_core_io.py`: `load_frozen_supply` verifies the four canonical C hashes and builds indices, reference locations and household HOME anchors; `write_gzip_rows` has deterministic compression (`mtime=0`, empty filename) and `write_json` has stable formatting.
- `src/simfleet_edg/spatial/escort_event_index.py`: `index_frozen_m2` preserves original event keys and reference pandas median semantics; **read only**, do not recompute synthetic links.
- `src/simfleet_edg/spatial/escort_target_anchor_extension.py`: `read_core_stable`, `extend_stable_anchors`, `AnchorAssignment`; the FULL sidecar CSV is frozen and must only be read, never recomputed or overwritten in the official F4.2b-B stage.
- `src/simfleet_edg/spatial/escort_synthetic_relations.py`: uses fixed hypothetical variants and one proposal per ESCORT event; do **not** call `propose()` for new draws or re-run synthetic relation generation.
- `src/simfleet_edg/spatial/escort_location_binding.py`: `inherit_location` references existing C `LocationRef` objects for accepted WORK/EDUCATION target anchors.
- `src/simfleet_edg/repro/f4_2b_a_local_sensitivity.py`: official source and strict old lineage gate; **protected**. The new F4.2b-B launcher must implement its *own new* real-clone lineage gate for the new commit, not try to call the B2a official runner gate (which is bound to its own HEAD).

## MAIN entry disposition

The scientifically frozen design remains exactly F4.2b-B `DESIGN_FROZEN_V1`; this packet authorises **implementation PREOPEN only after real-clone gate**. Scientific executions may occur ONLY post-push if every formal entry precheck, input hash, 11-variant scope, and previously frozen F4.2a/F4.2b-A protections pass. User performs commit/push manually via PyCharm. `F4.2c=NOT_OPEN`, `G3=NOT_OPEN`, `CAL=DO_NOT_REOPEN`, `MiD TEST=DO_NOT_READ`.
