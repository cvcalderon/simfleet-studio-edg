# SimFleet-EDG — F4.1c-C
## Operational LocationSupply + ResidentialAnchor — DESIGN FREEZE v2

**Status:** `DESIGN_FROZEN`  
**Implementation:** `NOT AUTHORIZED BY THIS ARTIFACT`

### Critical geography distinction

C v2 freezes two different geographic concepts and forbids conflating them:

```text
M1 BEZIRK = 12 Berlin administrative boroughs
LOR BZR   = 143 Bezirksregionen
```

The accepted M1 household field `home_zone_id` is the full14 BEZIRK code. Residential materialization must preserve that exact parent. LOR is used to construct geometry and later identify realized PLR/LOR_BZR/PGR, not to replace the M1 parent with one of 143 BZR.

### Residential bridge

For validated M1 code `110000000000XX`, `XX` is the two-digit borough code. Frozen LOR BZR and PLR IDs use the same two-digit prefix. A synthetic borough polygon is constructed as the union of all 143 frozen LOR-BZR polygons sharing `XX`. Exactly 12 unions must result.

Residential OSM polygons are clipped to these 12 unions. Selection mass is clipped area. Buildings are preferred absolutely over `landuse=residential`; sampling is with replacement because no dwelling capacity is available.

### HOME realization

One anchor is created for each of 54,828 accepted M1 households. Building anchors use `point_on_surface` of the clipped building fragment. The fallback landuse path uses deterministic SHA-256 keyed rejection sampling. The canonical `ResidentialAnchor.parent_bezirk_id` stores the exact full14 M1 code.

The final point is then mapped to a frozen PLR, LOR_BZR and PGR for evidence only. Its two-digit LOR prefix must equal the M1 borough suffix.

### Non-home supply

Operational non-home locations remain one physical record per OSM element. `attractiveness=None` and `capacity=None`. OUTSIDE records are excluded from operational supply. Multi-purpose eligibility is preserved. Potential duplicates are not merged.

The B MAIN-reconciled inside-Berlin purpose-label totals become C consistency anchors:

```text
BUSINESS      21,936
EDUCATION      7,227
LEISURE       36,463
OTHER          8,602
SHOPPING      22,436
WORK_COMMUTE  59,344
```

### No PLR imputation

The 27 PLR purpose gaps and residential gaps `03400831`, `06200418` remain observations. They are not targets and are not filled. M1 never had PLR home targets.

### Boundary

C materializes the supply universe and HOME anchors only. It assigns no non-home destination. `S_NEAR`, `S_DIST`, `S_ATTR` and G3 remain closed.
