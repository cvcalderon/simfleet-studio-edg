# SimFleet-EDG — F4.1c-A4
## Attractiveness / Capacity Evidence Policy Freeze — DRAFT v1

**Status:** DESIGN_DRAFT_READY_FOR_FREEZE  
**Repository mutation:** NO  
**OSM acquisition:** NO  
**Spatial candidate execution:** NO  
**G3 CAL/TEST:** FORBIDDEN  

## 1. Objective

Freeze what spatial evidence may later support:

```text
attractiveness
capacity
residential-anchor sampling mass
```

without confusing those concepts with A3 eligibility.

The frozen separation remains:

```text
Eligibility
= hard semantic compatibility.

Attractiveness
= soft relative opportunity evidence among already eligible locations.

Capacity
= structural person-slot constraint only when its unit, purpose and time basis are defensible.
```

The external OSM reference explicitly distinguishes attraction/capacity from simple POI existence and derives capacities from an additional external table because generic OSM capacity coverage was very sparse. Therefore this project must not infer general capacity from tags or geometry alone.

## 2. Existing canonical contract and consequence

The repository contract currently permits:

```python
LocationSupplyRecord.attractiveness: float | None
LocationSupplyRecord.capacity: float | None
```

Both fields are optional.

This is scientifically useful:

```text
None = evidence not yet defensible
```

and is preferable to filling the contract with fabricated numbers.

## 3. Major A4 finding: scalar-field ambiguity

A3 permits:

```text
one physical location
-> multiple eligible purposes
```

For example:

```text
library
-> EDUCATION
-> LEISURE
-> WORK_COMMUTE
```

But one scalar:

```text
attractiveness
capacity
```

cannot in general represent three different purpose-specific opportunity concepts.

For example:

```text
number of workers
!=
number of visitors
!=
education-place capacity
```

Therefore A4 SHALL NOT force purpose-specific evidence into one scalar merely because the canonical object has that field.

### V1 resolution

The base F4.1c-C materialization SHALL use:

```text
LocationSupplyRecord.attractiveness = None
LocationSupplyRecord.capacity       = None
```

and SHALL preserve raw evidence in a sidecar:

```text
LocationSupplyEvidenceRecord
```

F4.2 must freeze the exact transformation from that evidence to an effective `S_ATTR` weight before candidate execution.

This does **not** remove `S_ATTR`; it prevents A4 from pre-committing to an arbitrary scoring rule.

## 4. Residential-anchor mass

HOME is not generic LocationSupply.

For an eligible residential building polygon:

```text
residential_mass_proxy
=
projected footprint area in m²
```

This is permitted as a **relative sampling mass**, not a person capacity.

Interpretation:

```text
larger residential footprint
-> more residential opportunity mass
```

NOT:

```text
larger residential footprint
-> known number of residents
```

This is compatible with the reviewed eqasim-Bavaria design, where residential building surface is used as a selection weight rather than asserted as occupancy ground truth.

### Residential fallback

If a parent geography lacks adequate eligible residential-building support, an A3:

```text
landuse=residential
```

polygon may provide fallback sampling area.

Its projected area may weight fallback areas relative to other fallback areas.

It SHALL NOT compete at equal priority with explicit residential buildings.

## 5. Non-home raw attractiveness evidence

### Explicit polygon facility

For a purpose-eligible facility represented by a polygon:

```text
projected_area_m2
```

may be retained as raw attractiveness evidence.

It is not yet an operational weight.

### Point facility

For a point-only eligible facility:

```text
unit_presence = 1
```

may be retained as minimal opportunity evidence.

This does not claim that all point facilities have equal real-world importance.

### Area fallback

Large land-use polygons may retain:

```text
projected_area_m2
```

for diagnostics.

However, raw area SHALL NOT be used directly as V1 `S_ATTR` weight because a large land-use polygon could dominate explicit facilities merely because of its spatial extent.

## 6. Why A4 does not freeze an area transformation

Possible transformations include:

```text
area
sqrt(area)
log(1 + area)
purpose-wise normalization
winsorized/clipped relative mass
```

Choosing one before seeing the Berlin evidence distribution would be arbitrary.

Choosing one after seeing CAL performance would risk post-hoc tuning.

Therefore the correct sequence is:

```text
A4
freeze allowed raw evidence
    ↓
B
acquire + audit raw evidence distributions
    ↓
F4.2 PREOPEN
freeze exact S_ATTR transformation / seed / thresholds
    ↓
candidate execution
```

B may report distributions and outliers, but may not tune against G3 CAL.

## 7. Capacity policy

### V1 default

```text
capacity = NULL
```

for operational LocationSupply unless a future version explicitly validates a purpose-specific capacity field.

Unknown capacity means:

```text
UNKNOWN
```

not:

```text
0
```

and not:

```text
unlimited measured capacity
```

### Raw OSM capacity-like evidence

If the A2 snapshot contains capacity-like tags, they may be retained verbatim in the sidecar for audit.

They SHALL NOT automatically become:

```text
LocationSupplyRecord.capacity
```

because the same lexical field may refer to different real-world units depending on the feature.

Before any structural use, a capacity source must define:

```text
purpose
unit
population / visitor scope
time basis
provenance
validation rule
```

### Explicit prohibitions

V1 forbids:

```text
building area -> people capacity
land-use area -> people capacity
POI count -> people capacity
building levels -> people capacity
OSM category -> invented default capacity
```

The external OSM methodology could provide capacities only by introducing an additional capacity source/model; the tag mapping itself was not sufficient.

## 8. building:levels and floor-area proxies

A4 allows a raw building-level attribute to be preserved if encountered.

However:

```text
footprint_area × building_levels
```

is **not** an operational V1 attractiveness or capacity field.

Reasons:

- availability/quality has not yet been audited;
- level semantics can vary;
- multi-purpose use remains unresolved;
- the transformation would add complexity without current validation.

It may become a future ablation after a separate freeze.

## 9. Name/address evidence

Name and address are identity/canonicalization evidence only.

They may help resolve:

```text
POI node
+
containing building
```

as a possible duplicate under A3.

They SHALL NOT increase attractiveness and SHALL NOT imply capacity.

## 10. Missing evidence behavior

Two important invariants:

```text
attractiveness missing
!= location ineligible

capacity missing
!= capacity zero
```

Therefore missing A4 evidence must not delete an A3-eligible location.

The later S_ATTR candidate must explicitly define its neutral treatment for missing attractiveness before execution.

## 11. Capacity and assignment horizon

A structural capacity is meaningless unless its accounting horizon is defined.

Potential meanings include:

```text
simultaneous occupancy
daily visitors
employees assigned to workplace
students assigned to institution
households/residents
```

These are not interchangeable.

A4 V1 therefore refuses to use a generic scalar capacity until this scope is purpose-specific and frozen.

This also avoids an invalid operation such as treating a building's simultaneous occupancy as a daily number of synthetic destinations.

## 12. Evidence sidecar

F4.1c-C should materialize a provenance-rich sidecar conceptually containing:

```text
location_id
source_snapshot_id
osm_element_type
osm_element_id
geometry_evidence_class
projected_area_m2
osm_capacity_raw
building_levels_raw
attractiveness_evidence_class
capacity_evidence_class
provenance_notes
```

The exact repository schema is an implementation decision to be reviewed before C.

The base physical `LocationRef` remains unique; A4 does not create fake per-purpose duplicate locations.

## 13. Required B audit

After acquisition, B must report without tuning:

```text
eligible records with polygon area
point-only eligible facilities
area distributions by supply class
area distributions by eligible purpose
capacity-like tag prevalence and raw value patterns
building-level prevalence / parseability
explicit-facility vs fallback-area shares
residential-building coverage by Bezirk / PLR
extreme-area outliers
```

This audit answers:

> What evidence exists?

It does not yet answer:

> Which S_ATTR formula wins?

## 14. Interaction with S_NEAR / S_DIST / S_ATTR

### S_NEAR

Does not need A4 attractiveness/capacity.

### S_DIST

Uses the frozen M2 distance prior and does not need A4 attractiveness/capacity.

### S_ATTR

May later use A4 evidence, but only after F4.2 freezes the effective weighting rule.

For V1:

```text
capacity component
= neutral / inactive while capacity is NULL
```

unless an explicit A4 amendment introduces defensible capacity evidence before the candidate freeze.

Thus `S_ATTR` remains testable without inventing capacity.

## 15. Complexity rule

The project principle remains:

```text
Complexity must earn its place.
```

Therefore A4 deliberately starts with:

```text
residential footprint mass
+
raw non-home geometry evidence
+
unit evidence for point facilities
+
NULL structural capacity
```

rather than introducing unvalidated floor-area, employee or occupancy models.

Future enrichments must be evaluated as explicit ablations.

## 16. Proposed state

```text
F4.1c-A1 = DESIGN_DRAFT_READY_FOR_FREEZE
F4.1c-A2 = DESIGN_DRAFT_READY_FOR_FREEZE
F4.1c-A3 = DESIGN_DRAFT_READY_FOR_FREEZE
F4.1c-A4 = DESIGN_DRAFT_READY_FOR_FREEZE

repository mutation = NO
OSM acquisition = NO
spatial candidate execution = NO
G3 = NOT OPEN
```

Next:

```text
F4.1c-A5
ACQUISITION AUTHORIZATION / PREOPEN
```

A5 must audit A1–A4 jointly, resolve any blocking inconsistency, freeze exact acquisition scope and authorize only:

```text
download
integrity/provenance audit
schema/tag inventory
support audit
```

It must still forbid destination assignment and G3 candidate execution.
