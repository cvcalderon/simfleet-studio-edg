# SimFleet-EDG — F3.2b materializer implementation note v1

**Parent design freeze:** `25345916d80c7d810bb7d4699bfa056ed28cc4e8`  
**Purpose:** implement the F3.2a frozen TRAIN/CAL materialization contract.  
**Training:** none. **CAL inspection:** none. **TEST:** sealed.

## Implementation

`simfleet_edg.demand.training_data` materializes the eight frozen empirical tables for `TRAIN` and `CALIBRATION` only. Source household/person records remain the empirical fitting evidence; R4 synthetic rows are hash-validated interface witnesses and are never consumed as fitting rows.

The implementation preserves:

- household-atomic R2 partition inheritance;
- task-specific universes rather than a universal complete-case table;
- `P_GEW` / `W_GEW` as weight columns, never behavioural features;
- source/provenance IDs as keys, never behavioural features;
- ownership/access separation and resource top-coding;
- source weekday/season only as fitting analogues for scenario-known calendar context;
- observed upstream state only as explicitly tagged fit/teacher-forcing analogues;
- raw `wegkm` as primary distance target;
- explicit missing optional context and deterministic backoff compatibility;
- absence of mode, route, execution and `km_routing` from materialized schemas.

## Output

Default root:

```text
artifacts/model_data/F3_2a_training_data_v1/
```

with separate `TRAIN/` and `CALIBRATION/` directories, plus source-hash validation, row counts, schema snapshot, vocabulary manifest, materialization manifest, validation table and recursive SHA-256 checksums. No `TEST/` directory is created.

## Determinism

Tables use frozen canonical sort keys and UTF-8/LF CSV serialization with `%.17g` float formatting. A local dry-run from the frozen source bytes reproduced all 16 row-count anchors and a second independent materialization produced byte-identical files.
