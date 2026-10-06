# F4.1b — M2→M3 Canonical Adapter + LOR Environment Gate v1

## Status

`PREOPEN_IMPLEMENTATION_NOT_COMMITTED`

Required parent: `8ccbb4d54601a7fdf65fe6cb549e688d2ba1558e`.

F4.1b implements only the engineering bridge frozen by F4.1a. It does not
spatialize any person, household, activity, or trip.

## Upstream binding

The canonical adapter is bound to the row schema emitted by the frozen F3.4g
joint generator:

```text
PA1
→ COUNT_REF
→ CHA2
→ TIME_B_TB2
→ DIST_REF_REFERENCE
```

Historical F3 component snapshots that still say `formal_g2=NOT_EVALUATED`
remain untouched. The authoritative later closure state is
`G2=PASS_CLOSED_DO_NOT_REOPEN`.

## Runtime boundary

`src/simfleet_edg/repro/f3_4g2a_joint_synthetic.py` is reproduction/evaluation
code, not the M3 runtime API.

F4.1b therefore implements a pure adapter from *already-generated* day/trip
rows into `PersonDayPlan`. It does not execute D_GEN, read CAL, or read TEST.

The exact frozen source row schema is recorded in
`F4_1B_CANONICAL_M2_M3_CONTRACT_v1.json`.

## Identity note

The historical joint-generator schema carries `source_household_id` and
`source_person_id`. In this adapter those values are preserved as the canonical
household/person identifiers of the input rows. A later production D_GEN binding
must feed P_CONSTR runtime identities explicitly; F4.1b does not pretend that the
historical synthetic cohort is the accepted M population.

## Geospatial environment

Minimal required extra:

```toml
spatial = [
  "shapely>=2,<3",
  "pyproj>=3.7,<4",
]
```

GeoPandas and Fiona are intentionally not required.

Source LOR CRS is `EPSG:4326`.

The frozen metric working CRS for geometric distances/areas is `EPSG:25833`
(ETRS89 / UTM zone 33N). This is a design choice for Berlin metric geometry; it
does not change source GeoJSON bytes.

## LOR gate

The gate checks:

- exact frozen source hashes;
- expected PLR/BZR/PGR feature counts;
- unique IDs;
- geometry presence;
- non-empty geometry;
- Shapely validity;
- finite WGS84 bounds;
- finite projected bounds;
- positive projected area;
- PLR→BZR and BZR→PGR parent completeness;
- consistent parent assignments.

Passing this gate establishes that the LOR geometry framework is technically
usable. It does **not** establish a residential mass model or an activity
location supply.

## Scientific boundary

F4.1b does not authorize:

- home-anchor assignment;
- activity-location assignment;
- `S_NEAR`;
- `S_DIST`;
- `S_ATTR`;
- candidate selection;
- G3 CAL;
- G3 TEST.

The next phase after a clean F4.1b freeze is
`F4.1c — Location Supply Design & Evidence Binding`.
