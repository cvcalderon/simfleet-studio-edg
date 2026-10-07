# SimFleet-EDG — F4.1c-A5
## Joint Freeze Review & Acquisition Authorization — v1

**Decision:** `PASS_WITH_NONBLOCKING_BINDINGS`  
**Authorized next phase:** `F4.1c-B — Acquire + audit external supply`  
**Operational LocationSupply materialization:** NOT AUTHORIZED  
**Destination / home assignment:** NOT AUTHORIZED  
**F4.2 candidates:** NOT AUTHORIZED  
**G3:** NOT OPEN  

## 1. Purpose

A5 is not a fifth independent model-design step. It is the joint consistency gate for A1–A4.

The gate asks:

> Are purpose semantics, source identity, OSM eligibility and evidence semantics sufficiently coherent to acquire the frozen external dataset without contaminating downstream candidate design?

The answer is:

```text
YES — with non-blocking bindings that do not affect raw acquisition/audit.
```

## 2. Joint result

The A1–A4 set is internally coherent on the major scientific boundaries:

```text
A1  defines what M3 is resolving.
A2  defines which external bytes may be used.
A3  defines which raw OSM semantics are eligible.
A4  defines which extra evidence may be retained without inventing weights/capacity.
```

The separation is preserved:

```text
purpose semantics
!= source identity
!= eligibility
!= attractiveness evidence
!= capacity
!= candidate scoring
```

## 3. Normative reconciliation

One wording ambiguity was found.

A1 section 7 listed `ESCORT` in the general destination-purpose vocabulary for `LocationSupplyRecord`. However:

- A1 defines ESCORT as `RELATIONAL`;
- A1 forbids an arbitrary ESCORT→POI rule;
- A3 excludes ESCORT from generic location-supply purposes.

A5 therefore freezes the authoritative V1 interpretation:

```text
Generic LocationSupplyRecord.eligible_purposes =
    WORK_COMMUTE
    BUSINESS
    EDUCATION
    SHOPPING
    LEISURE
    OTHER
```

while:

```text
RETURN_HOME -> ResidentialAnchor
ESCORT      -> relational resolver
```

This is a clarification, not a scientific redesign.

## 4. Source verification before authorization

The Geofabrik Germany index currently exposes the exact dated artifact:

```text
berlin-261004.osm.pbf
```

with an index size of approximately 95 MB and the corresponding `.md5` sidecar.

Thus A2's dated snapshot identity is operationally discoverable at A5 review time.

The actual provider MD5, local SHA-256, PBF header timestamp and bounding box are **not** frozen from web metadata. They must be captured from the downloaded bytes during B.

## 5. Why B is now authorized

B can now answer empirical supply questions without changing model semantics:

```text
How many OSM objects match A3?
Which tags remain unmapped?
How much residential-building evidence exists?
How much non-home supply exists by purpose?
How much is point-only vs polygon?
How large are the area distributions?
How frequent are raw capacity-like fields?
Where are support gaps by PLR/BZR?
How many possible POI/building duplicates exist?
```

Those questions require the raw PBF but do not require a destination-assignment algorithm.

## 6. Closed-world audit rule

A3 remains frozen during B.

If B discovers a frequent useful tag not present in A3:

```text
DO NOT add it inside the worker run.
```

Instead:

```text
B evidence
-> MAIN
-> versioned A3 amendment
-> new hash
-> rerun affected B audits
```

This prevents post-hoc registry design against the observed Berlin supply.

## 7. A4 behavior during B

B may retain raw evidence such as:

```text
projected polygon area
capacity-like tag text/value
building-level raw value
point-vs-polygon evidence class
```

but shall not turn it into:

```text
final attractiveness
structural person capacity
S_ATTR score
```

The canonical operational fields remain unresolved until the downstream freeze.

## 8. Open bindings that do not block B

### F4-BIND-A4-SIDECAR-001

The evidence sidecar is conceptually defined but its exact repository schema is not yet implemented.

```text
blocks B = NO
blocks C = YES
```

B may use audit-only tabular evidence.

### F4-BIND-ESCORT-001

The linked-person relation needed by relational ESCORT remains unresolved.

```text
blocks B = NO
blocks F4.2 execution containing ESCORT = YES
```

### F4-BIND-002-R

The final deterministic point-realization rule inside residential evidence is still open.

```text
blocks B = NO
blocks C ResidentialAnchor materialization = YES
```

### F4-BIND-007

Outside-Berlin destination policy remains open.

```text
blocks Berlin-only B audit = NO
required before F4.2 if external-destination semantics are needed
```

## 9. Exact A5 authorization

A5 authorizes only:

```text
download exact dated PBF
download provider MD5
integrity verification
local SHA-256
PBF metadata inspection
A3 tag/rule audit
A4 raw-evidence audit
LOR support audit
audit-only derived tables
manifest / environment / log / checksums
```

A5 does not authorize:

```text
operational LocationSupply materialization
ResidentialAnchor assignment
destination assignment
ESCORT fallback
S_NEAR
S_DIST
S_ATTR
attractiveness tuning
capacity inference
G3 CAL
G3 TEST
candidate selection
```

## 10. Required F4.1c-B output

B must return a compact RunBundle containing at minimum:

```text
acquisition_manifest.json
environment.json
pbf_metadata.json
integrity checks
A3 rule-application counts
unmapped tag inventory
purpose-supply counts
geometry-quality audit
facility/fallback audit
duplicate audit
A4 area/capacity-like evidence audit
residential support by PLR/BZR
non-home support by PLR/BZR
F4_1C_B_AUDIT_SUMMARY.md
checksums.sha256
```

Large extracted audit tables may remain on Proxmox and be referenced by checksum.

## 11. Gate result

```text
F4.1c-A1 = FROZEN_BY_A5_OVERLAY
F4.1c-A2 = FROZEN_BY_A5_OVERLAY
F4.1c-A3 = FROZEN_BY_A5_OVERLAY
F4.1c-A4 = FROZEN_BY_A5_OVERLAY

F4.1c-A5 = PASS_WITH_NONBLOCKING_BINDINGS

F4.1c-B acquisition/audit = AUTHORIZED
F4.1c-C materialization   = NOT AUTHORIZED
F4.2 candidate execution = NOT AUTHORIZED
G3                       = NOT OPEN
```

## 12. Next operational step

The next work item is no longer conceptual A-design.

It is:

```text
F4.1c-B
ACQUIRE + AUDIT EXTERNAL LOCATION SUPPLY EVIDENCE
```

under the exact scope in:

```text
F4_1C_A5_ACQUISITION_PREOPEN_v1.yaml
```

Before implementing the worker inside the project repository, the authoritative GitHub snapshot at the frozen HEAD should be inspected so that the acquisition/audit code, configs and tests are added with exact repository scope rather than ad-hoc notebook logic.
