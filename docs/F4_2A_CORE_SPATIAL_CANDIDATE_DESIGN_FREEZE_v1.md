# SimFleet-EDG — F4.2a
## Core Spatial Candidate Semantics & Pre-G3 Design Freeze — v1

**Workflow:** `SIMFLEET_EDG_WORKFLOW_V2`  
**State:** `DESIGN_FROZEN`  
**Implementation:** `NOT AUTHORIZED`

## 1. Phase decomposition

F4.2 is split into:

```text
F4.2a — core candidate semantics (non-ESCORT)
F4.2b — relational ESCORT
F4.2c — integrated spatialization + G3
```

This prevents inventing an ESCORT POI simply to make the core candidate experiment executable.

## 2. Frozen activity semantics

```text
HOME                    -> frozen ResidentialAnchor
WORK / EDUCATION        -> one stable location per person
BUSINESS / SHOPPING /
LEISURE / OTHER         -> one location per activity occurrence
ESCORT                  -> excluded from F4.2a core; unresolved until F4.2b
```

Repeated WORK/EDUCATION reuse the same location. Occurrence activities preserve activity-node continuity.

## 3. Distance compatibility

`distance_prior_km` remains an M2 prior, not exact OD truth, not routing distance, and not mode-specific distance.

All geometric distance uses straight-line EPSG:25833 separation.

For prior `p>0` and separation `d>=0`:

```text
C_dist = 0                    if d = 0
C_dist = min(d/p, p/d)        otherwise
```

`C_dist` is only a multiplicative compatibility ranking. It does not claim that Euclidean distance equals the surveyed trip distance.

## 4. Stable WORK / EDUCATION

Stable locations are determined independently of processing order.

For each person-purpose:

```text
collect incoming trips to purpose
if HOME-origin incoming trips exist:
    target_prior = median(their distance_prior_km)
else:
    target_prior = median(all incoming distance_prior_km)

candidate origin = person's frozen HOME anchor
```

The selected location is reused for every occurrence of that stable purpose.

## 5. Occurrence activities

For BUSINESS, SHOPPING, LEISURE and OTHER, each non-ESCORT day is traversed by `trip_index`.

```text
origin = already resolved current activity
prior  = incoming trip distance_prior_km
```

The selected activity location becomes both the incoming trip destination and the next trip origin.

## 6. Candidate families

### S_NEAR

Diagnostic baseline only: choose nearest purpose-eligible location. Tie: `location_id`.

### S_DIST

Primary V1 candidate: choose maximum `C_dist`.

Tie order:

```text
1. prefer d <= p
2. smaller |d-p|
3. location_id
```

### S_ATTR

Experimental ablation only.

F4.1c-C froze canonical attractiveness and capacity as NULL, so S_ATTR is not treated as a validated behavioral attractiveness model.

For each purpose, positive-area polygons receive:

```text
q = (rank - 0.5) / n
A_evidence = 0.5 + q
```

Point/missing-area records receive `A_evidence=1.0`; capacity multiplier is always `1.0`.

```text
S_attr = C_dist * A_evidence
```

S_ATTR is not selectable in V1.

## 7. Pre-registered promotion rule

Roles are frozen before execution:

```text
S_NEAR = diagnostic baseline
S_DIST = only promotable V1 core candidate
S_ATTR = ablation
```

S_DIST may become `M3_CORE_SELECTED` only if all hard invariants pass and:

```text
median_abs_log_ratio(S_DIST) <= median_abs_log_ratio(S_NEAR)
mean_abs_log_ratio(S_DIST)   <= mean_abs_log_ratio(S_NEAR)
p90_abs_log_ratio(S_DIST)    <= p90_abs_log_ratio(S_NEAR)
```

No practical margin will be tuned after seeing results. Failure returns to MAIN; no silent fallback.

## 8. Determinism

All policies are deterministic.

```text
seed schedule = NONE_DETERMINISTIC
```

Tie-breaking is explicit. Official execution must be rerun and exact output hashes compared.

## 9. ESCORT

A1 prohibited `ESCORT -> arbitrary POI`.

Because PersonDayPlan contains no explicit escorted-person relation, F4.2a excludes an entire day plan if it contains ESCORT.

Required reporting:

```text
escort days
escort persons
escort activities
share of valid days excluded
share of valid persons affected
```

No coverage threshold is invented before execution. Full M3 closure remains blocked until F4.2b.

## 10. Outside Berlin

`F4-BIND-007` is resolved for V1 as `BERLIN_CLOSED_WORLD`.

Only the frozen Berlin operational supply is eligible. Long distance priors do not authorize synthetic outside-Berlin destinations.

## 11. PLR gaps

Search is citywide over purpose-eligible Berlin supply. No local-PLR candidate requirement exists, so observed PLR purpose gaps do not trigger imputation or synthetic POIs.

## 12. G3 status

F4.2a is pre-G3 core characterization.

```text
G3 = NOT OPEN
MiD TEST = DO NOT READ
independent exact spatial TEST = NOT AVAILABLE V1
```

Structural and distance metrics characterize the core policy; integrated G3 is deferred until the relational ESCORT problem is resolved.

## 13. Current state

```text
F4.1c-C = CLOSED_PASS
F4.2a   = DESIGN_FROZEN
F4.2a implementation = NOT AUTHORIZED

F4-BIND-007        = RESOLVED_FOR_V1
F4-BIND-ESCORT-001 = OPEN_BLOCKING_FULL_M3

G3 = NOT OPEN
```

Next: repository-entry audit at commit `eebccc7a43eb7c1ef2661da3f357c0e5b01e72ef`, then F4.2a Worker Packet.
