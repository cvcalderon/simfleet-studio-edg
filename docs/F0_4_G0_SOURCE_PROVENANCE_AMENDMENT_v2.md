# F0.4 / G0 — Source provenance amendment v2

## Status

`APPROVED_PROVENANCE_AMENDMENT_FOR_R1_REPRODUCTION`

## Trigger

The first official R1 run (`R1_source_audit_v1`) failed exactly one required byte check:
`Z22_BERLIN_GLOSSARY`.

- R1 expected the F0.4 locally rebaselined hash: `ebd66160413268167b9962876aca4ff9bd46b7ea76eefb6e77955149b1662e4f`.
- The staged source file had: `a4f3e5884a3ba4966a29c63eede4f20844b6cc673da1dc06f975717926ee2bdf`.
- That staged hash is the same hash frozen in F0.1 for the official Zensus glossary.
- A fresh user download from the documented official endpoint during R1 diagnosis also produced `a4f3e588...`.

The `ebd661...` identity is only evidenced as a locally mounted F0.4 copy. Its source bytes are not currently preserved in the reproducibility handoff and the current official download does not reproduce it.

## Revised decision

For **source-byte reproducibility**, the canonical R1 identity of `Z22_BERLIN_GLOSSARY` is restored to:

`a4f3e5884a3ba4966a29c63eede4f20844b6cc673da1dc06f975717926ee2bdf`

The former F0.4 local-copy hash is retained as historical provenance:

`ebd66160413268167b9962876aca4ff9bd46b7ea76eefb6e77955149b1662e4f`

and is classified as `SUPERSEDED_LOCAL_COPY_IDENTITY`, not an accepted alternative hash for R1.

## Why this does not silently rewrite G0

This amendment follows the post-G0 freeze rule:

1. **new evidence:** R1 byte audit + fresh official-source download;
2. **previous decision:** F0.4 rebaseline to `ebd661...`;
3. **revised decision:** reproducible source identity restored to `a4f3e588...`;
4. **new artifact version:** this amendment + R1 config v3;
5. **impact assessment:** below.

## Impact assessment

- Zensus glossary semantics used downstream: **UNCHANGED**.
- Population/demand contracts: **UNCHANGED**.
- MiD/Zensus mappings: **UNCHANGED**.
- F1/F2 generated results: **NO NUMERIC IMPACT**; the glossary is documentation/semantic evidence, not a fitted numeric data table.
- G0 overall readiness: remains **SUPERADO**, with corrected provenance.
- R1 first official attempt: remains **FAIL** and is preserved as evidence.
- Next R1 execution must use a new retry run ID.

## Reproducibility rule

R1 must require one exact canonical hash, not a multi-hash allowlist. This keeps byte identity strict while preserving the superseded local hash in provenance metadata.
