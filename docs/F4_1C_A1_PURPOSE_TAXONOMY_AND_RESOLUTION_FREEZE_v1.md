# SimFleet-EDG — F4.1c-A1
## Purpose Taxonomy & Resolution Semantics Freeze — DRAFT v1

**Status:** DESIGN DRAFT / NO REPOSITORY MUTATION / NO ACQUISITION

## 1. Objective

Freeze how each runtime CHA2 activity is interpreted by M3 before any external spatial evidence is acquired.

M3 consumes the frozen runtime activity vocabulary:

- HOME
- WORK
- BUSINESS
- EDUCATION
- ESCORT
- LEISURE
- OTHER
- SHOPPING

M3 does not change activity purpose, timing, trip count, mode, route, service or execution outcome.

## 2. Activity-to-purpose primitive

The frozen destination-purpose primitive remains:

| Runtime activity | Destination purpose |
|---|---|
| HOME | RETURN_HOME |
| WORK | WORK_COMMUTE |
| BUSINESS | BUSINESS |
| EDUCATION | EDUCATION |
| ESCORT | ESCORT |
| LEISURE | LEISURE |
| OTHER | OTHER |
| SHOPPING | SHOPPING |

Historical/training-only labels are not promoted into the M3 runtime taxonomy.

## 3. Resolution classes

M3 SHALL distinguish four resolution classes.

### 3.1 HOUSEHOLD_ANCHOR

**Activity:** HOME

- Resolved through `ResidentialAnchor`, not through generic `LocationSupplyRecord` lookup.
- Exactly one stable synthetic home anchor per household for the simulation realization/horizon.
- All household members share the same anchor.
- Every HOME activity node for that household resolves to exactly the same `LocationRef`.
- The accepted M1 Bezirk remains a hard parent geography, not an exact point.
- Exact MiD home coordinates are unavailable and SHALL NOT be claimed or reconstructed.

### 3.2 PERSON_STABLE_SUPPLY

**Activities:** WORK, EDUCATION

- Resolved from eligible external supply.
- Once assigned for a person in a population/spatial realization, the primary location is stable across all same-type activity occurrences for that person.
- Repeated WORK activity nodes SHALL resolve to the same assigned WORK location unless a future explicitly versioned multi-workplace extension is introduced.
- Repeated EDUCATION activity nodes SHALL resolve to the same assigned EDUCATION location unless a future explicitly versioned multi-institution extension is introduced.
- Stability is a spatial-realization property; it does not alter the upstream activity chain.

### 3.3 OCCURRENCE_SUPPLY

**Activities:** BUSINESS, SHOPPING, LEISURE, OTHER

- Each distinct activity node is resolved once from purpose-eligible external supply.
- The chosen location is reused for the incoming destination and outgoing origin of that activity node, preserving spatial chain continuity.
- Different occurrences of the same activity type may resolve to different locations.
- `OTHER` SHALL use only an explicitly curated eligibility registry. It SHALL NOT be an unrestricted fallback to all POIs.

### 3.4 RELATIONAL

**Activity:** ESCORT

- ESCORT is not treated as a generic independent POI category.
- Preferred semantics: the location is inherited from a linked person's relevant destination/activity anchor.
- Current `PersonDayPlan` does not contain an explicit escorted-person relation; therefore the concrete relation mechanism remains an OPEN binding.
- Until this binding is resolved, an arbitrary `ESCORT -> any eligible POI` rule is FORBIDDEN.
- Any future proxy/fallback must be explicitly named, versioned and evaluated; it cannot silently become the core semantics.

## 4. Activity-node continuity

M3 spatializes activity nodes, not trips independently.

For a chain:

```text
A0 --T1--> A1 --T2--> A2
```

M3 SHALL assign exactly one location to `A1` and enforce:

```text
T1.destination == A1.location == T2.origin
```

This is required even when A1 is an occurrence-based activity.

## 5. HOME continuity

For any household `h` with anchor `H_h`:

```text
forall HOME activity nodes a belonging to h:
location(a) = H_h
```

No HOME activity may be resolved via another residential building simply because it is geographically closer to the preceding activity.

## 6. Upstream semantics preserved

- `return_home=false` SHALL NOT be changed to true by M3.
- M3 SHALL NOT append a HOME activity.
- M3 SHALL NOT change `final_activity`.
- M3 SHALL NOT use selected mode, route, routing outcome, service feasibility or execution outcome.
- `DIST_REF_REFERENCE` remains an M2 distance prior, not an exact OD target.

## 7. LocationSupply semantics

`LocationSupplyRecord.eligible_purposes` SHALL use the destination-purpose vocabulary:

```text
WORK_COMMUTE
BUSINESS
EDUCATION
SHOPPING
ESCORT
LEISURE
OTHER
```

`RETURN_HOME` is normally resolved through `ResidentialAnchor`, not the generic supply pool.

A physical location MAY be eligible for multiple purposes. The same OSM-derived object need not be duplicated solely because it supports WORK and BUSINESS, or WORK and SHOPPING, etc.

## 8. Runtime taxonomy exclusions

The following historical/training labels SHALL NOT become runtime M3 supply classes solely because they exist in historical artifacts:

- NON_HOME_UNKNOWN
- PRIVATE_ERRAND
- SCHOOL
- CHILD_HOMECARE
- HOMEMAKER
- OTHER_ACTIVITY

Any future promotion requires a separate versioned contract change.

## 9. Open bindings after A1

| Binding | Status | Required before | Description |
|---|---|---|---|
| F4-BIND-001-R | REASSIGNED_OPEN | F4.1c-C | residential evidence/mass source within accepted Bezirk |
| F4-BIND-002-R | REASSIGNED_OPEN | F4.1c-C | deterministic/versioned point realization rule for residential anchor |
| F4-BIND-003 | PARTIALLY_RESOLVED_BY_A1 | F4.1c-A3 | tag-to-purpose supply eligibility registry |
| F4-BIND-004 | OPEN | F4.1c-C | operational activity-location supply |
| F4-BIND-005 | OPEN | F4.1c-A4 | attractiveness evidence/features |
| F4-BIND-006 | OPEN | F4.1c-A4 | structural capacity evidence/fields |
| F4-BIND-ESCORT-001 | NEW_OPEN | before F4.2 execution containing ESCORT | linked-person / escort-location resolution mechanism |
| F4-BIND-007 | OPEN | before F4.2 | outside-Berlin policy |
| F4-BIND-008 | OPEN | before F4.2 | candidate seed policy |
| F4-BIND-009 | OPEN | PRE-CAL/G3 | G3 metrics and thresholds |

## 10. A1 acceptance conditions

A1 can be frozen only if all are accepted:

1. Runtime taxonomy is exactly the selected CHA2 vocabulary.
2. Historical labels are not silently promoted.
3. HOME uses stable household anchor semantics.
4. WORK and EDUCATION use person-stable primary-location semantics.
5. BUSINESS/SHOPPING/LEISURE/OTHER use occurrence-supply semantics.
6. OTHER is curated, not universal fallback.
7. ESCORT is relational and no generic POI fallback is silently authorized.
8. Activity-node spatial continuity is mandatory.
9. M3 remains mode/route/execution blind.
10. No OSM acquisition, destination assignment or candidate execution occurs in A1.

## 11. Next phase after A1

`F4.1c-A2 — External Spatial Source & Acquisition Contract Freeze`

A2 must define source identity, geographic extent, snapshot provenance, acquisition mechanism, hashes, licensing/provenance metadata and raw-data storage policy before any OSM acquisition.
