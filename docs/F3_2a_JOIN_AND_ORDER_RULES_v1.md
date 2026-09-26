# F3.2a — Join, retention and deterministic order rules v1

## 1. Join backbone

`source_household_id = H_ID` and `source_person_id = HP_ID` are technical lineage keys only. They are never model features.

1. Select only frozen strict `TRAIN` or strict `CALIBRATION` households from the R2 SplitManifest.
2. Join `Personen.H_ID` to the selected household IDs.
3. Join `Haushalte` 1:1 on `H_ID` to obtain source-side household resource state.
4. Recode age/sex/activity/resources using only frozen mappings.
5. Join F0.3 task-specific evidence by `HP_ID`; trip evidence uses `(HP_ID,W_ID)`.
6. `W_GEW` for transition/spatial rows is joined from the F0.3d trip-time audit by `(HP_ID,W_ID)`, matching the accepted R7 reconstruction.

No TEST outcome row is ever selected or materialized.

## 2. Calendar analogue

Fitting uses source reference-day context only as the analogue of a future known scenario calendar:

- `ST_WOTAG` -> `source_weekday` -> runtime `scenario_weekday`;
- `saison` -> `source_season` -> runtime `scenario_month_or_season`.

`ST_MONAT` is retained only as provenance in core v1. `feiertag` was deliberately deferred by F3.1c and is not added by F3.2a.

## 3. Task-specific row retention

There is no universal complete-case table.

- participation: `mobil_diff in {0,1,2,3,5}`;
- count: `CORE_STRICT_COUNT` and `K>0`;
- chain days: full functional daily sequence;
- chain transitions: eligible transitions **intersected with full-functional days**;
- timing: every `DIRECT_TEMPORAL_VALID` row;
- distance primary: every direct `DIRECT_SOURCE_DISTANCE_VALID` row;
- expanded distance: frozen raw+source-imputed sensitivity universe.

Optional contextual missingness does not change these universes.

## 4. Source analogues of upstream generated state

Observed K/activity/time values may appear in downstream fitting tables only because at runtime those fields are supplied by already-generated upstream D_GEN state. They must be tagged `UPSTREAM_SOURCE_ANALOGUE` and cannot be confused with same-target predictors.

- TRAIN: source analogues may be used to fit the downstream conditional model.
- isolated CAL component evaluation: source analogues may be teacher-forced as frozen in F3.1c.
- propagated CAL/runtime: selected upstream generated state replaces them.

## 5. Explicit incomplete context

Do not silently drop rows when optional upstream context is unavailable.

Frozen audits show:

- timing rows all join a transition record, but not all transitions are fully eligible/resolved;
- raw distance has 32 TRAIN and 11 CAL rows without a `DIRECT_TEMPORAL_VALID` counterpart;
- raw distance has 217 TRAIN and 27 CAL rows whose transition context is not fully eligible.

Such rows remain in the target universe with explicit quality/status fields and deterministic backoff. `UNKNOWN` from the source and `__MISSING_CONTEXT__` from an unavailable optional join remain different states.

## 6. Deterministic order

Person-day tables sort by `(source_household_id, source_person_id)`. Trip-level tables sort by `(source_household_id, source_person_id, source_trip_id)`. Prefix fields are reconstructed only after this canonical ordering. Candidate/model code may not depend on the incidental order of source CSV files.

## 7. Serialization

Training tables are deliberately canonical CSV rather than Parquet because the frozen empirical tables are small (maximum ~6k rows per primary table) and byte-auditable CSV avoids introducing a pyarrow-version dependency at this stage. Large later synthetic/runtime outputs may still use Parquet.
