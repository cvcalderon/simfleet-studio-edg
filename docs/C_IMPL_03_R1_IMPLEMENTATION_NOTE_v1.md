# C-IMPL-03 / R1 Source Audit — implementation note v1

## Purpose

Implement the PRE-F3 R1 source audit without modifying, normalising or redistributing raw source data.

## Frozen behaviour

R1 verifies:

- exact SHA-256 of the frozen F0 source baseline;
- required-file presence;
- MiD CSV dimensions and a minimal set of known required columns;
- Zensus workbook sheet counts;
- LOR GeoJSON feature counts;
- ZIP integrity;
- Git identity and clean/synchronised execution state.

Raw data are never copied into the RunBundle or committed to Git.

## Scope

The configuration contains 17 source artefacts:

- 8 MiD artefacts;
- 5 Zensus artefacts, of which statistical blocks are optional;
- 4 LOR artefacts.

There are 16 R1-gating required artefacts and one optional artefact.

## Interpretation

A hash mismatch is a hard R1 failure. R1 does not repair, redownload or silently replace an input. A different source byte sequence must be investigated before R2.
