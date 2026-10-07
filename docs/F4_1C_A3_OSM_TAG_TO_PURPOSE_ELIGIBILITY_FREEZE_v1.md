# SimFleet-EDG — F4.1c-A3
## OSM Tag-to-Purpose Eligibility Registry — DESIGN DRAFT v1

**Status:** DESIGN_DRAFT_READY_FOR_FREEZE  
**Repository mutation:** NO  
**OSM acquisition:** NO  
**Candidate execution:** NO  
**G3 CAL/TEST:** FORBIDDEN  

## 1. Objective

Freeze the **eligibility semantics** that will later convert raw OSM objects from the A2 snapshot into:

- residential-anchor evidence; or
- purpose-eligible `LocationSupplyRecord` candidates.

A3 does **not** define attractiveness or capacity.

The three layers remain strictly separate:

```text
Eligibility   = hard semantic compatibility
Attractiveness = later soft weight
Capacity       = later structural constraint
```

## 2. Source-derived evidence vs project-specific design

The external methodological reference demonstrates four points that are directly useful here:

1. raw OSM objects can be extracted from nodes, ways and relations;
2. a practical destination inventory can be built from a restricted family of primary keys;
3. one physical object may legitimately support multiple activity types;
4. raw OSM tags alone do not provide reliable general-purpose capacities.

The paper's extraction key family is:

```text
amenity
building
craft
healthcare
landuse
leisure
office
shop
historic
tourism
```

It then manually classified key-value pairs into activity types. The published table is explicitly **exemplary**, not a complete registry.

Therefore, the SimFleet-EDG registry below is **not claimed to reproduce the full Malkus et al. mapping**. It is a conservative project-specific V1 mapping grounded in the frozen CHA2 semantics and in the cited OSM methodology.

## 3. Critical semantic non-equivalence

The Malkus activity type called `private business` must **not** be mapped automatically to SimFleet-EDG `BUSINESS`.

In our frozen CHA2 contract:

```text
BUSINESS -> BUSINESS
OTHER    -> OTHER
```

A source activity labelled “private business” can represent personal errands rather than work-related business travel.

Therefore, for example:

```text
amenity=recycling
```

is mapped in this draft to:

```text
OTHER + WORK_COMMUTE
```

rather than blindly to `BUSINESS`.

This rule prevents a label-name collision from becoming a scientific-semantic error.

## 4. Default-deny architecture

The registry is **closed-world**:

```text
known high-priority rule -> apply
otherwise                 -> EXCLUDE_UNMAPPED
```

No unseen OSM tag becomes eligible merely because it exists in the acquired snapshot.

This is essential because A3 is frozen **before** B acquisition. The subsequent B audit may reveal unmapped tags, but adding one requires a versioned registry change rather than silent runtime admission.

## 5. Rule precedence

Rules are evaluated by descending `priority`.

Order:

```text
1. lifecycle/inactive exclusions
2. explicit exclusions
3. HOME-anchor rules
4. purpose-specific include rules
5. area-fallback rules
6. purpose guards
7. default deny
```

An exclusion at higher priority overrides a lower include rule.

## 6. HOME and ESCORT remain outside generic LocationSupply

A3 preserves A1:

```text
HOME   -> ResidentialAnchor
ESCORT -> RELATIONAL
```

Thus:

- `RETURN_HOME` is forbidden in generic `LocationSupplyRecord.eligible_purposes`;
- `ESCORT` is forbidden in generic OSM supply;
- residential tags are evidence for anchor materialization, not ordinary destination POIs.

## 7. Multi-purpose locations are allowed

A single physical object may expose several eligible purposes.

Example:

```text
amenity=library
-> EDUCATION
-> LEISURE
-> WORK_COMMUTE
```

This follows both the project contract and the external methodological evidence that one OSM object can support multiple activity types.

The runtime representation should remain:

```text
one canonical physical LocationRef
+
eligible_purposes = (...)
```

rather than duplicating physical geometry into independent fake locations.

## 8. Core mapping families

### HOME anchors

Direct building evidence:

```text
building =
  apartments
  residential
  house
  detached
  semidetached_house
  terrace
  bungalow
```

`landuse=residential` is only a fallback residential **area**, not a capacity-bearing building and not a generic location record.

`building=yes` remains excluded because it carries insufficient semantic information.

### WORK / BUSINESS

Core direct evidence includes:

```text
office=*
craft=*
building=office|industrial|commercial|retail|warehouse
landuse=industrial|commercial  [area fallback]
```

Selected institutions, shops, healthcare and visitor-serving facilities may also be eligible for `WORK_COMMUTE` because they physically employ people.

`BUSINESS` is narrower than `WORK_COMMUTE` and is concentrated on office/craft/commercial/industrial and explicitly business-oriented facilities.

### EDUCATION

Core evidence:

```text
amenity=
  school
  university
  college
  kindergarten
  childcare
  language_school
  music_school
  driving_school

building=
  school
  university
  college
  kindergarten
```

`amenity=library` is explicitly multi-purpose:

```text
EDUCATION + LEISURE + WORK_COMMUTE
```

### SHOPPING

Core evidence:

```text
active shop=*
amenity=marketplace
building=retail|commercial
landuse=retail [area fallback]
```

`shop=vacant` is explicitly excluded.

### LEISURE

Core families:

```text
active leisure=*
selected visitor-serving amenity=*
selected tourism=*
selected historic=*
landuse=forest [area fallback]
```

The V1 registry deliberately does **not** enable all `tourism=*` or all `historic=*`.

### OTHER

`OTHER` is a curated union, not a universal fallback.

V1 includes selected:

```text
healthcare=*
health amenities
civic/public services
social/religious destinations
selected personal-service destinations
```

Transport/mode infrastructure is not admitted as generic OTHER supply.

## 9. Mode-blind guardrail

The spatializer remains mode-blind.

Objects whose primary semantics are transport infrastructure are not used merely because they could be trip endpoints:

```text
parking
bicycle parking
fuel
charging station
bus station
taxi
car wash
```

This avoids leaking a downstream mode/service assumption into M3.

## 10. Geometry policy

A3 freezes geometry semantics for later materialization:

```text
OSM node
-> node coordinate

closed way / multipolygon relation
-> point_on_surface for runtime point representation
```

A generic centroid rule is rejected because centroids of concave or multipart polygons may fall outside the represented facility.

Invalid geometries are excluded and audited.

Area-level rules (`landuse=*`, large leisure polygons, etc.) are tagged explicitly as **fallback areas** and must not silently compete at the same semantic priority as an explicit facility.

## 11. Canonicalization / duplicate policy

OSM may describe one real-world place through both a POI node and a building/area.

The V1 policy is conservative:

```text
same OSM object + multiple recognized tags
-> one canonical record with union of eligible purposes
```

For distinct OSM objects:

```text
POI node inside building
-> merge only with strong identity evidence
```

Strong identity evidence is:

- matching normalized name with compatible semantics; or
- matching normalized address with compatible semantics.

Pure geometric containment is **not** sufficient to merge.

Unresolved possible duplicates remain separate but are flagged for the B/C audit.

This prefers visible duplicate uncertainty over aggressive false merging.

## 12. Lifecycle policy

Inactive or future objects are excluded.

Examples:

```text
disused:*
abandoned:*
demolished:*
razed:*
removed:*
proposed:*
construction:*
```

and explicit inactive values such as:

```text
vacant
construction
demolished
abandoned
disused
proposed
```

No lifecycle object may become supply through a lower-priority include rule.

## 13. Important divergence from the external example

The paper's exemplary table includes mappings that are not automatically adopted here.

Examples:

- `landuse=forest` was mapped to leisure + work; SimFleet-EDG V1 keeps it only as a **LEISURE area fallback**.
- `building=terrace` was not used as a POI in the example; SimFleet-EDG may use it as **residential anchor evidence**, because residential-anchor semantics differ from generic POI semantics.
- `building=commercial` had shopping/work/education in the example; SimFleet-EDG does not automatically inherit `EDUCATION` from such a broad tag.
- `amenity=recycling` used the paper's “private business” category; SimFleet-EDG maps it to `OTHER`, avoiding a false equivalence with CHA2 `BUSINESS`.

These are intentional, versioned project choices.

## 14. B-stage audit required after acquisition

After A5 authorizes acquisition and B obtains the PBF, the registry must be audited without changing it.

Required counts:

```text
raw objects by key/value
matched include rules
lifecycle exclusions
explicit exclusions
unmapped default-deny objects
eligible supply by purpose
geometry type
explicit facility vs area fallback
potential duplicate pairs
coverage by Bezirk and PLR
```

The purpose of this audit is to answer:

> Does the frozen registry produce operationally sufficient spatial support?

It is **not** permission to modify the registry opportunistically.

If support is insufficient, B returns evidence to MAIN and a versioned A3 amendment is opened before C materialization.

## 15. What A3 does not define

Still OPEN for A4:

```text
attractiveness
capacity
area-derived weighting
explicit OSM capacity semantics
capacity NULL policy details
S_ATTR weighting
```

Still forbidden:

```text
home assignment
destination assignment
S_NEAR
S_DIST
S_ATTR
candidate selection
G3 CAL
G3 TEST
MiD TEST
G1/G2 reopen
```

## 16. Proposed state

```text
F4.1c-A1 = DESIGN_DRAFT_READY_FOR_FREEZE
F4.1c-A2 = DESIGN_DRAFT_READY_FOR_FREEZE
F4.1c-A3 = DESIGN_DRAFT_READY_FOR_FREEZE

OSM acquisition = NO
repository mutation = NO
spatial candidate execution = NO
```

Next:

```text
F4.1c-A4
ATTRACTIVENESS / CAPACITY EVIDENCE POLICY FREEZE
```
