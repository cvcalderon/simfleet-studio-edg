# F4.1c-C — Design v1 Supersession / v2 Correction

**Status:** `v1 SUPERSEDED BEFORE IMPLEMENTATION`  
**Replacement:** `F4_1C_C_OPERATIONAL_SUPPLY_AND_RESIDENTIAL_ANCHOR_DESIGN_FREEZE_v2`

The v1 draft used the label `BZR` where the hard M1 residential parent is actually the **12-district BEZIRK geography**. This is not the same object as the frozen LOR `BZR` layer of 143 Bezirksregionen.

No F4.1c-C implementation or execution had been authorized, so the correction is made entirely at DESIGN_FREEZE time. F4.1c-B is unaffected.

Authoritative terminology from v2:

```text
M1_BEZIRK = 12 administrative boroughs, full14 codes 11000000000001..12
LOR_BZR   = 143 Bezirksregionen, 6-digit IDs
LOR_PLR   = 542 Planungsräume, 8-digit IDs
```

Bridge:

```text
M1 full14 -> last two digits -> 01..12
LOR_BZR/PLR -> first two digits -> 01..12
M1 BEZIRK polygon -> union of frozen LOR_BZR polygons with matching prefix
```

The v2 design also changes the duplicate sidecar field from one scalar group ID to a JSON array, because a physical OSM object may participate in multiple diagnostic duplicate groups (for example NAME/ADDRESS and multiple semantic buckets). No destructive merge is introduced.
