# SimFleet-EDG — F3.2a training-data/materialization contract v1

**Parent:** `58bb4183a9557b8b8b069552813db9530cb848b0`  
**Entry:** F3.1 model-design freeze SUPERADO  
**Status:** FROZEN CONTRACT; materializer implementation not yet executed  
**G1:** OPEN · **formal G2:** NOT EVALUATED · **TEST:** SEALED

## Objective

Freeze the exact empirical tables that F3.2b–g are allowed to consume, before implementing encoders or fitting any candidate.

The contract separates three layers:

```text
source/provenance keys + weights
        !=
semantic feature context X
        !=
task target y
```

IDs and survey weights are required for audit/estimation but never become behavioural predictors.

## Physical split isolation

Materialization root:

```text
artifacts/model_data/F3_2a_training_data_v1/
  TRAIN/
  CALIBRATION/
```

There is deliberately **no `TEST/` directory**. CAL tables can later be consumed only by the frozen F3.1c evaluation/selection code; F3.2 training code must accept TRAIN paths only.

## Dataset family

Eight logical tables are frozen per allowed partition:

1. `person_day_context` — shared M1/calendar/source-resource context;
2. `participation`;
3. `trip_count`;
4. `chain_days`;
5. `chain_transitions`;
6. `time_trips`;
7. `distance_raw`;
8. `distance_expanded_sensitivity` (report-only).

The expected row counts are frozen in `F3_2a_EXPECTED_ROW_COUNTS_v1.csv`.

## Resource semantics

Source-side TRAIN/CAL resource context is reconstructed from MiD `Haushalte`/`Personen` using the same canonical semantics as M1. The synthetic R4 population is **not** fitting evidence. R4 persons/households/resources are retained only as runtime-interface compatibility witnesses.

`Ownership != Access != Availability(t)` remains hard. Dynamic availability is not materialized as a D_GEN feature.

## No complete-case drift

Each component retains its F3.1 task-specific empirical universe. Missing optional upstream context becomes explicit status/backoff state; it does not silently shrink the target sample.

## Calendar semantics

`ST_WOTAG` and `saison` are fitting analogues for scenario-known weekday/season. They are not donor values copied into a generated day. Month is provenance-only in core v1; holiday remains deferred by F3.1c.

## Output identity

The future materializer must produce exact source-hash validation, exact row-count validation, frozen schemas/vocabularies, canonical row order, byte SHA-256 checksums and a manifest that records parent commit/config/source identities.

## Non-goals

F3.2a does not implement encoders, fit models, inspect CAL metrics, select A/B, or open TEST.
