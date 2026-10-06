# F4.1a — M3 Contract & Spatial Supply Design Freeze v1

## Status

`PREOPEN_DESIGN_FROZEN_NO_IMPLEMENTATION`

This starts formal F4/M3 after authoritative G1/G2 closure. It does not execute D_GEN, read MiD TEST, implement a spatializer, or select `S_NEAR`, `S_DIST`, or `S_ATTR`.

## Frozen upstream

```text
M1 = P_CONSTR_RMIN_V2_HD_U / M
M2 = PA1 -> COUNT_REF -> CHA2 -> TIME_B_TB2 -> DIST_REF_REFERENCE
G1 = PASS_CLOSED
G2 = PASS_CLOSED_DO_NOT_REOPEN
MiD TEST = CONSUMED_BY_G2_DO_NOT_REOPEN
```

M3 consumes these artifacts. It may not refit or retune them.

## Entry finding

The accepted population has `home_zone_level=BEZIRK` and 12 home-zone IDs. Therefore the home field is district context, not a usable point location. A finer synthetic residential realization is required.

## M3 boundary

M3 assigns synthetic physical locations to already-generated activities and produces `SpatializedDayPlan`. It does not decide participation, trip count, purpose, timing, mode, route, service, or execution outcome. Destination realization precedes M5 mode choice.

The implementation must introduce explicit contracts for `PopulationSnapshotAdapter`, `PersonDayPlan`, `TripDemand`, `LocationRef`, `ActivityIntent`, `SpatialTripIntent`, `SpatializedDayPlan`, `ResidentialAnchor`, and `LocationSupplyRecord`.

## Residential anchors

A household receives one stable home anchor for the simulation horizon and all household members share it. The accepted M1 Bezirk is a hard parent geography, not a point. Exact MiD home coordinates are unavailable and must never be claimed as reconstructed.

## Spatial framework

LOR 2021 is frozen as geographic framework, not as complete activity supply: 542 PLR, 143 BZR, 58 PGR, EPSG:4326, `MultiPolygon`. Topology validity is deferred to F4.1b because Shapely was absent in F4.0c. No operational purpose-specific POI/building supply is frozen yet.

## Eligibility, attractiveness, capacity

Eligibility is a hard purpose-compatibility filter. Attractiveness is a soft positive weight among eligible candidates. Capacity is a separate structural constraint. External/OSM supply is candidate evidence, not ground truth.

## Distance semantics

`DIST_REF_REFERENCE` is an M2 trip-distance prior. It is not exact OD, route length, or mode-specific path length. F4 must explicitly define how that prior constrains geometric origin-destination separation.

## Candidate families

No winner is selected in F4.1a. `S_NEAR` is the diagnostic nearest-eligible baseline; `S_DIST` uses the M2 distance prior; `S_ATTR` additionally uses declared attractiveness/capacity evidence. Scoring, tolerances, seeds, and selection thresholds must be frozen before candidate CAL/selection.

## Next authorized phase

`F4.1b — M2->M3 canonical adapter + LOR environment gate`.
