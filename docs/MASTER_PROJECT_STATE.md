# SimFleet-EDG — MASTER PROJECT STATE v1

**As of:** 2026-10-07  
**Workflow:** `SIMFLEET_EDG_WORKFLOW_V2`  
**Workflow status:** `MAIN_ADOPTED / REPOSITORY_SYNC_PENDING`

## 1. Why this document exists

This file is the first navigation/state document for every new SimFleet-EDG thread.

It does not replace frozen scientific contracts. It tells the reader:

- what is closed;
- what is frozen;
- what is synchronized in Git;
- what is only frozen in MAIN's control plane;
- which evidence is sealed/consumed;
- which bindings remain open;
- what exact task is currently authorized.

## 2. Traceability baseline

Source archive:

```text
F0-F4_1c.zip
```

Exact non-directory inventory:

```text
files             = 281
ZIP artifacts      = 205
Closure ZIPs       = 40
Development ZIPs   = 157
```

This exact recount supersedes the earlier approximate conversational count.

Archive SHA-256:

```text
e4f8930040f8b14fd205f930d1dc0bc79958af5980ce87aa09525638ab607bf2
```

The historical archive remains immutable evidence. Workflow V2 applies prospectively.

## 3. Architecture state

```text
M0 = CLOSED / ACCEPTED
M1 = CLOSED / ACCEPTED
M2 = CLOSED / ACCEPTED
M3 = IN PROGRESS
M4 = NOT STARTED
M5 = NOT STARTED
M6 = NOT STARTED
M7 = NOT STARTED
```

## 4. Gate state

```text
G0 = PASS / CLOSED
G1 = PASS / CLOSED / FROZEN
G2 = PASS / CLOSED / FROZEN / DO NOT REOPEN
G3 = NOT OPEN
```

Sealed evidence:

```text
MiD TEST = CONSUMED_BY_G2_DO_NOT_REOPEN
F1 CAL   = CLOSED_DO_NOT_REOPEN
```

After the G2 holdout:

```text
candidate tuning = FORBIDDEN
threshold tuning = FORBIDDEN
same-lineage scientific tuning = FORBIDDEN
```

## 5. Accepted population

```text
candidate = P_CONSTR_RMIN_V2_HD_U
scale     = M

persons    = 100,000
households = 54,828

strict:
  households = 54,026
  persons    = 93,127

6+:
  households = 802
  persons    = 6,873

home_zone_level = BEZIRK
```

The 12 Bezirke are residential context, not exact household coordinates.

## 6. Frozen M2 pipeline

```text
participation = DG_PARTICIPATION::PART_A::PA1
trip_count    = DG_TRIP_COUNT::COUNT_REF::REFERENCE
activity_chain= DG_ACTIVITY_CHAIN::CHAIN_A::CHA2
time_schedule = TIME_B_TB2
distance_prior= DIST_REF_REFERENCE
```

No refit, CAL reopen or MiD TEST reopen is allowed.

## 7. M3 / F4 state

### F4.1a

```text
state  = CLOSED_PASS
commit = 8ccbb4d54601a7fdf65fe6cb549e688d2ba1558e
```

### F4.1b

```text
state  = CLOSED_PASS
commit = 7e28e80c32dc16c478ea6916b636bafa58e917f5
```

### F4.1c-A

```text
state = DESIGN_FROZEN
repository sync = 0958a673f0527b5bc87c16cb041e620f085ead87 lineage
A1/A2/A3/A4 = frozen
A5 = PASS_WITH_NONBLOCKING_BINDINGS
```

### F4.1c-B

```text
state = CLOSED_PASS
implementation commit = 0958a673f0527b5bc87c16cb041e620f085ead87
source snapshot = OSM_GEOFABRIK_BERLIN_2026-10-04_V1
MAIN qualifier = PASS_WITH_MAIN_LOR_REPORTING_RECONCILIATION
```

### F4.1c-C

```text
state = IMPLEMENTATION_PREOPEN
design = F4_1C_C_OPERATIONAL_SUPPLY_AND_RESIDENTIAL_ANCHOR_DESIGN_FREEZE_V2
required parent = 0958a673f0527b5bc87c16cb041e620f085ead87
official materialization = ONLY AFTER EXACT IMPLEMENTATION COMMIT + PUSH
```

Critical geography:

```text
M1 BEZIRK = 12 administrative boroughs / full14 IDs
LOR BZR   = 143 Bezirksregionen / 6-digit IDs
```

### F4.2

```text
NOT AUTHORIZED
```

## 8. Expected repository entry state

Before any C edit on the real clone:

```text
branch      = main
HEAD        = 0958a673f0527b5bc87c16cb041e620f085ead87
origin/main = 0958a673f0527b5bc87c16cb041e620f085ead87
worktree    = clean
```

The C baseline archive is `F0-F4_1c-B-repo.zip` with SHA-256
`aae1ee4e4036cd2c5d339122738ef1b3dc4940b768f3cd0bdfd899fe417ab8db`.
It contains no `.git`; the real-clone gate remains authoritative.

## 9. F4.1c-C frozen inputs

```text
OSM snapshot = OSM_GEOFABRIK_BERLIN_2026-10-04_V1
OSM SHA256   = 056a47f9e4cd6e510acf62ac1c1da4c4740a6ff7be97946b7596ae1ea5090ae2
M1 households= 54,828
M1 persons   = 100,000
home parent  = BEZIRK full14 11000000000001..12
LOR          = 542 PLR / 143 BZR / 58 PGR
network      = FORBIDDEN
```

## 10. Binding state

```text
F4-BIND-A4-SIDECAR-001 = RESOLVED_V2
F4-BIND-001             = RESOLVED_V2
F4-BIND-002-R           = RESOLVED_V2
F4-BIND-007             = OPEN / OUTSIDE remains audit-only
F4-BIND-ESCORT-001      = OPEN / blocks later F4.2 ESCORT cases
```

## 11. Current prohibitions

Do not:

```text
reopen G1 or G2
read MiD TEST
retune F1 or M2
assign non-home destinations
execute S_NEAR / S_DIST / S_ATTR
open F4.2
open G3
infer capacity or canonical attractiveness
merge potential duplicate OSM entities destructively
use network access in C
run authoritative C materialization before the exact implementation commit is pushed
push from terminal
```

## 12. Exact next authorized task

```text
F4.1c-C
Operational LocationSupply + ResidentialAnchor Materialization
```

Execution flow:

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
→ PRE-COMMIT STOP
```

The user performs commit + push from PyCharm. Only then:

```text
post-push freeze
→ materialization C
→ second full reproducibility run
→ compare exact output SHA-256
→ RunBundle
→ return to MAIN
```
