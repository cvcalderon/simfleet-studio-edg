# SimFleet-EDG — F4.1c-B
## Implementation + Audit PREOPEN — v1

**Workflow:** `SIMFLEET_EDG_WORKFLOW_V2`  
**Parent:** `7e28e80c32dc16c478ea6916b636bafa58e917f5`  
**Scope:** acquire the exact dated Geofabrik Berlin OSM PBF and produce audit-only evidence.  
**Runtime spatialization:** forbidden.

### Baseline erratum applied

MAIN corrected only the protected SHA-256 for `src/simfleet_edg/canonical/mobility.py` to:

```text
881fd12eb59d89ebe48a30a1e5f267f55051720dc265471ca796f154afcb9d2e
```

The correction is technical only. A1–A5 scientific semantics remain frozen.

### Implementation boundary

The implementation adds an isolated `osm` dependency extra, exact-dated source acquisition,
data-driven A3 registry evaluation, audit-only OSM evidence extraction, RunBundle generation,
and preopen/RunBundle verifiers.

It does **not** materialize operational `LocationSupplyRecord` or `ResidentialAnchor` objects,
assign households or activities, execute `S_NEAR`, `S_DIST`, or `S_ATTR`, open G3, read MiD TEST,
or reopen G1/G2.

### Acquisition freeze guard

`--precheck` is network-free and may be executed before commit.

`--acquire-and-audit` requires the implementation to be frozen in a clean Git commit different
from the parent commit. This prevents official OSM acquisition from being tied to uncommitted
implementation bytes.

### Exact source

```text
snapshot = OSM_GEOFABRIK_BERLIN_2026-10-04_V1
PBF      = https://download.geofabrik.de/europe/germany/berlin-261004.osm.pbf
MD5      = https://download.geofabrik.de/europe/germany/berlin-261004.osm.pbf.md5
```

Mutable `latest` aliases are forbidden.

### Integrity hierarchy

Provider MD5 is transfer integrity only. The project identity is the locally computed SHA-256.
Raw PBF bytes are immutable and gitignored. Existing raw bytes are reused only when they match
the provider MD5; mismatching bytes are never overwritten silently.

### Audit semantics

The A3 registry is loaded from the frozen CSV. Exclusion rules precede inclusion, unknown tags
are closed-world default-deny, multi-tag matches union eligible purposes, and HOME/ESCORT remain
outside generic supply. A4 retains projected area and capacity-like fields as raw evidence only;
no people-capacity or attractiveness score is inferred.

Metric geometry evidence uses `EPSG:25833`. Polygon audit points use point-on-surface semantics.
Potential duplicates are flagged only; no destructive merge occurs.

### PRE-COMMIT gate

The Worker must complete:

```text
focused tests
→ Ruff
→ mypy
→ full regression
→ preopen verifier
→ exact-scope audit
```

No terminal `git push` is authorized.
