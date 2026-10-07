# SimFleet-EDG — F4.1c-A2
## External Spatial Source & Acquisition Contract Freeze — DRAFT v1

**Date:** 2026-10-06  
**Phase:** F4.1c-A2 — External spatial evidence contract  
**Status:** `DESIGN_DRAFT_READY_FOR_FREEZE`  
**Repository mutation:** NO  
**External acquisition:** NO  
**Spatialization:** NO  

---

## 1. Objective

Freeze the identity and acquisition semantics of the external spatial evidence that will later feed:

- residential-anchor evidence;
- operational `LocationSupplyRecord` materialization;
- purpose-specific eligibility mapping;
- optional attractiveness evidence;
- explicit capacity evidence where defensible.

This step does **not** define the OSM tag-to-purpose registry (F4.1c-A3), does **not** infer capacity (F4.1c-A4), and does **not** download the source yet (F4.1c-A5).

---

## 2. Authoritative source family

```text
upstream_dataset = OpenStreetMap
upstream_owner/community = OpenStreetMap contributors
extract_provider = Geofabrik GmbH
format = OSM PBF (.osm.pbf)
source_role = RAW_EXTERNAL_SPATIAL_EVIDENCE
```

Rationale:

1. OSM provides the raw building/POI/land-use/tag evidence needed by F4.1c.
2. Geofabrik provides stable regional extracts and dated historical PBF artifacts.
3. `.osm.pbf` is preferred over Geofabrik's free shapefile/GeoPackage derivatives because those formats apply a provider-side layer/feature selection, while F4.1c-A3 still needs to decide which raw OSM tags are scientifically eligible.
4. Overpass is useful for diagnostics, but is not accepted as the authoritative V1 source because a live query is not, by itself, a frozen byte-identical snapshot.

---

## 3. Frozen V1 snapshot candidate

```text
source_snapshot_id = OSM_GEOFABRIK_BERLIN_2026-10-04_V1
provider_filename = berlin-261004.osm.pbf
provider_region = Berlin
provider = Geofabrik GmbH
format = osm.pbf
provider_file_date_label = 2026-10-04
provider_last_modified = 2026-10-05 17:11 (server index observation)
approx_provider_size = 95 MB
```

The dated filename is authoritative for acquisition. `berlin-latest.osm.pbf` is **forbidden** in reproducible runs.

The source contract intentionally freezes a contemporary 2026 spatial-supply snapshot. This extends the already hybrid Berlin reference and therefore must never be described as a single-year observed Berlin dataset.

```text
MiD behaviour        = 2017
LOR geography        = 2021
Zensus controls      = 2022
OSM spatial supply   = 2026-10-04 snapshot candidate
```

Temporal interpretation:

```text
BERLIN_HYBRID_REFERENCE_V1
+ contemporary frozen spatial-supply evidence
```

not:

```text
"Berlin observed in year X"
```

---

## 4. Geographic scope

### Raw acquisition domain

```text
Geofabrik Berlin extract
```

### Operational M3 domain V1

```text
Berlin study area defined by the already frozen LOR framework
```

The operational inclusion test must use the frozen project geometry (LOR union / project spatial boundary), not silently redefine Berlin from the provider extract polygon.

Therefore:

```text
retrieval_extent != operational_study_boundary
```

The Geofabrik extract is the raw evidence envelope; the frozen LOR geometry remains the project geographic frame.

### Outside-Berlin policy

Still open for F4.2.

F4.1c-A2 does not authorize outside-Berlin destination generation. If later design requires Brandenburg supply, this must create a **new source version / extension contract**, not silently switch the V1 source.

---

## 5. Required acquisition provenance

At F4.1c-A5/B acquisition time, the following fields become mandatory:

```text
source_snapshot_id
upstream_dataset
extract_provider
provider_filename
provider_download_url
provider_region
provider_date_label
retrieved_at_utc
http_last_modified          # if available
content_length_bytes        # if available
provider_md5_expected
provider_md5_observed
local_sha256
pbf_header_timestamp        # extracted after download if available
pbf_bbox                    # extracted after download
file_size_bytes
license_id
attribution_text
acquisition_tool
acquisition_tool_version
```

### Integrity rule

Acquisition succeeds only if:

```text
provider MD5 matches
AND local SHA256 is computed
AND PBF can be opened/read
AND PBF metadata/header audit succeeds
```

The project uses SHA-256 as its own authoritative content hash even if the provider publishes MD5 for transfer verification.

---

## 6. Raw-file immutability

The raw acquired bytes are immutable.

Recommended local path:

```text
data/raw/osm/berlin/2026-10-04/
  berlin-261004.osm.pbf
  berlin-261004.osm.pbf.md5
  acquisition_manifest.json
  LICENSE_OSM_ODBL.txt or license-reference metadata
```

Rules:

```text
NO overwrite
NO in-place update
NO "latest" alias as scientific input
NO automatic daily refresh
```

A newer OSM snapshot requires a new `source_snapshot_id` and explicit comparison/revalidation.

---

## 7. Git / storage policy

The PBF is a data artifact, not normal source code.

```text
Git repository:
  acquisition code
  config
  source manifest
  hashes
  tag registry
  validation/audit summaries

External/local data storage:
  raw .osm.pbf
  large derived Parquet/GeoParquet outputs
```

The Git-tracked manifest must be sufficient to identify the exact raw bytes used.

---

## 8. License and attribution

OSM data are licensed under the Open Data Commons Open Database License (ODbL) 1.0.

Required project attribution baseline:

```text
© OpenStreetMap contributors
Data available under ODbL 1.0
```

Geofabrik is recorded as the extract provider; OpenStreetMap contributors remain the data source attribution.

Any public distribution of derived database artifacts must be reviewed for ODbL attribution/share-alike obligations before release.

---

## 9. Public-extract privacy policy

Use only the public Geofabrik extract.

The public server removes contributor personal metadata fields such as username/user ID/changeset ID. The project has no need for the internal/full-history extract.

Therefore:

```text
public Geofabrik PBF = ALLOWED
internal/full-metadata OSM extract = FORBIDDEN / NOT REQUIRED
```

---

## 10. Provider-format policy

### Accepted authoritative input

```text
.osm.pbf
```

### Not accepted as authoritative V1 source

```text
berlin-latest.osm.pbf
live Overpass response
free .shp.zip
free .gpkg.zip
rendered tiles
Nominatim results
```

Reasoning:

- `latest` is mutable;
- Overpass is query-time state and may differ across time/endpoints;
- Geofabrik free SHP/GPKG are provider-derived/preselected representations and may omit tags/features needed by A3;
- rendered tiles/Nominatim are products/services, not the raw supply evidence contract.

They may be used for diagnostics only if clearly labelled non-authoritative.

---

## 11. Extraction boundary between A2 and A3

A2 freezes **where the bytes come from**.

A3 will freeze **which OSM objects/tags become eligible supply**.

Therefore A2 explicitly does not yet specify:

```text
amenity=...
building=...
office=...
shop=...
leisure=...
landuse=...
```

No raw OSM object is a `LocationSupplyRecord` merely because it exists in the PBF.

---

## 12. Extraction boundary between A2 and A4

A2 also does not define:

```text
attractiveness
capacity
```

OSM geometry/tag existence is evidence only.

The following remain prohibited until A4:

```text
building area -> person capacity
POI count -> capacity
OSM category -> invented capacity
```

---

## 13. Residential-anchor evidence

The same frozen OSM snapshot may supply residential evidence for `ResidentialAnchor`, but residential extraction rules belong to A3/A4/C.

A2 only authorizes the source family, not the rule.

This keeps:

```text
HOME -> ResidentialAnchor
```

separate from generic non-home `LocationSupplyRecord` selection.

---

## 14. Reproducibility invariant

Every derived spatial record must be traceable to:

```text
source_snapshot_id
+ source OSM element identity/type
+ extraction code version
+ eligibility-registry version
+ geometry transformation version
```

At minimum, derived data should preserve a stable source identity such as:

```text
osm_element_type
osm_element_id
```

when legally/technically present in the public extract.

---

## 15. Update policy

There is no silent refresh.

A future snapshot follows:

```text
new source snapshot
-> new acquisition manifest
-> source audit
-> tag/supply coverage comparison
-> impact assessment
-> explicit authorization
```

A new snapshot does not overwrite V1 results.

---

## 16. Known scientific limitation

OSM is volunteered geographic information. Presence, completeness and tagging quality vary by feature/activity class.

Therefore:

```text
OSM absence != real-world absence
OSM count != opportunity count
OSM tag != capacity
```

Coverage must be audited purpose by purpose after acquisition and before F4.2 candidate comparison.

---

## 17. F4.1c-A2 freeze candidate

Candidate decisions:

```text
SOURCE FAMILY
  OpenStreetMap via public Geofabrik extract

V1 ARTIFACT
  berlin-261004.osm.pbf

FORMAT
  raw .osm.pbf

REPRODUCIBILITY
  fixed dated artifact; latest forbidden

PROJECT HASH
  SHA-256 captured after acquisition

TRANSFER CHECK
  provider MD5 + local verification

RAW SCOPE
  Berlin Geofabrik extract

OPERATIONAL SCOPE
  frozen Berlin LOR framework

LICENSE
  ODbL 1.0 + © OpenStreetMap contributors attribution

UPDATE POLICY
  immutable; explicit new-version process only

OVERPASS
  diagnostic only; not authoritative

SHP/GPKG
  diagnostic only; not authoritative raw evidence
```

---

## 18. Status

```text
F4.1c-A2 = DESIGN_DRAFT_READY_FOR_FREEZE

repository mutation = NO
OSM acquisition = NO
F4.1c-A3 = NEXT
F4.1c-A5 acquisition authorization = NOT YET
```

### Next substep

`F4.1c-A3 — OSM Tag-to-Purpose Eligibility Registry Freeze`

A3 must define a versioned, declarative mapping from raw OSM evidence to the runtime purpose-resolution semantics frozen in A1, while preserving:

```text
eligibility != attractiveness != capacity
```
