# MAIN update — C-IMPL-03 / R1 provenance amendment v3

## Finding

R1 attempt 1 failed only `Z22_BERLIN_GLOSSARY` hash validation: 15/16 required hashes matched, 16/16 required structures matched.

## Root cause

F0.4 recorded a local glossary copy (`ebd661...`) as a rebaseline, but R1 staging and a fresh download from the documented official source both reproduce the original F0.1 identity (`a4f3e588...`). The rebaselined bytes are not preserved in the handoff.

## Decision

Restore `a4f3e588...` as the canonical reproducible source identity for R1; retain `ebd661...` as superseded local-copy provenance.

## Scientific impact

None on F1/F2 numeric results or source semantics. G0 remains SUPERADO with a provenance amendment.

## Execution rule

After committing this amendment on clean/synced `main`, rerun as `R1_source_audit_v1_retry01`. Preserve the original FAIL bundle.
