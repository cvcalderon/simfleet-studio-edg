# SimFleet-EDG — F4.1c-B
## MAIN RunBundle Review & Closure — v1

**Workflow:** `SIMFLEET_EDG_WORKFLOW_V2`  
**MAIN decision:** `PASS`  
**Scientific state:** `CLOSED_PASS`  
**Qualifier:** `PASS_WITH_MAIN_LOR_REPORTING_RECONCILIATION`

## 1. Integrity

Transfer archive SHA-256:

```text
483dee04c9a6e6e83fa50799a23b670c1c2ee94508d2e6c18ca8c1f6c8e742e4
```

This matches the Worker handoff.

Internal RunBundle checksum verification:

```text
entries checked = 20
PASS            = 20
FAIL            = 0
```

The TAR contains the expected 21 files: 20 payload files plus `checksums.sha256`.

## 2. Frozen implementation and source

```text
parent commit         = 7e28e80c32dc16c478ea6916b636bafa58e917f5
implementation commit = 0958a673f0527b5bc87c16cb041e620f085ead87
source snapshot        = OSM_GEOFABRIK_BERLIN_2026-10-04_V1
```

Source integrity:

```text
provider MD5 = e343658854412938f98a6bf4b54834f5
local SHA256 = 056a47f9e4cd6e510acf62ac1c1da4c4740a6ff7be97946b7596ae1ea5090ae2
size         = 99643774 bytes
PBF timestamp= 2026-10-04T20:20:21Z
PBF readable = True
```

The reused raw file is acceptable because its provider MD5 and project SHA-256 are fixed and verified. `retrieved_at_utc` is interpreted as the official-run verification/reuse time, not necessarily the first network-transfer instant.

## 3. A3 audit reconciliation

```text
relevant objects          = 859703
explicitly excluded       = 377089
default denied            = 184970
eligible valid            = 297642
invalid eligible geometry = 2
```

Exact reconciliation:

```text
377089
+ 184970
+ 297642
+ 2
= 859703
```

Geometry also reconciles:

```text
POINT valid   = 47823
POLYGON valid = 249819
total valid   = 297642
```

The two invalid eligible polygons were excluded, as required by A3.

## 4. MAIN LOR reconciliation

The Worker handoff counted the sentinel `OUTSIDE` as if it were an extra BZR/PLR.

That interpretation is not accepted.

Frozen LOR remains:

```text
BZR = 143
PLR = 542
```

After excluding `OUTSIDE`:

```text
real BZR represented                    = 143
BZR with residential support            = 143 / 143
BZR with all six non-home purposes      = 143 / 143

PLR with some non-home evidence          = 542 / 542
PLR with residential evidence            = 540 / 542
PLR lacking >=1 non-home purpose         = 27 / 542
```

The two PLR without residential support are:

```text
03400831
06200418
```

Missing non-home purpose by PLR:

```text
BUSINESS     = 5
EDUCATION    = 15
LEISURE      = 1
OTHER        = 13
SHOPPING     = 3
WORK_COMMUTE = 1
```

This is a reporting reconciliation, not a rerun requirement.

`OUTSIDE` remains audit evidence only and is NOT an operational LOR zone.

## 5. Inside-Berlin purpose evidence

The Worker `purpose_supply_counts.csv` includes labels on records outside the frozen LOR domain.

For downstream Berlin-domain interpretation, the authoritative label counts are:

```text
BUSINESS     = 21936
EDUCATION    = 7227
LEISURE      = 36463
OTHER        = 8602
SHOPPING     = 22436
WORK_COMMUTE = 59344
```

These are purpose-label counts, not unique physical-location totals.

The corresponding `OUTSIDE` diagnostic labels are retained separately and must not enter F4.1c-C operational Berlin supply unless a future explicit policy supersedes this restriction.

## 6. A4 boundary

```text
area-evidence groups        = 30
capacity-like occurrences   = 150148
parseable                    = 150136
non-parseable                = 12

canonical attractiveness    = NOT WRITTEN
canonical capacity          = NOT WRITTEN
```

A4 is respected.

## 7. Duplicate diagnostics

```text
potential identity groups = 11853
destructive merges         = 0
```

No duplicate group is accepted as ground truth. These remain diagnostic evidence.

## 8. Scientific decision

F4.1c-B has fulfilled its authorized purpose:

```text
acquire exact external source
→ cryptographic identity
→ A3 audit
→ A4 raw-evidence audit
→ LOR support audit
```

No forbidden spatialization occurred.

MAIN therefore closes:

```text
F4.1c-B = CLOSED_PASS
```

with the LOR reporting reconciliation above.

No A3 amendment is opened merely because B observed unmapped tags. No A4 evidence is promoted to capacity/attractiveness.

## 9. Next authorized transition

Only the **design** of F4.1c-C is now authorized:

```text
F4.1c-C
Operational LocationSupply Materialization Contract / PREOPEN
```

Implementation is NOT yet authorized.

Before C implementation, MAIN must resolve:

```text
F4-BIND-A4-SIDECAR-001
F4-BIND-002-R
residential allocation/mass rule as needed
inside-LOR materialization filter / OUTSIDE handling
canonical physical-entity / duplicate materialization semantics
```

`S_NEAR`, `S_DIST`, `S_ATTR` and G3 remain unopened.
