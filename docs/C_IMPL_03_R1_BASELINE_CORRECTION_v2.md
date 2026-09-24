# C-IMPL-03 / R1 — G0 baseline correction v2

## Status

`IMPLEMENTATION_CORRECTION_REQUIRED_BEFORE_R1_EXECUTION`

## Finding

The first R1 configuration used the historical F0.1 SHA-256 for `Z22_BERLIN_GLOSSARY`:

`a4f3e5884a3ba4966a29c63eede4f20844b6cc673da1dc06f975717926ee2bdf`

F0.4/G0 subsequently recorded an intentional documentation rebaseline after semantic revalidation. The frozen G0 byte identity used downstream is:

`ebd66160413268167b9962876aca4ff9bd46b7ea76eefb6e77955149b1662e4f`

R1 reproduces the **frozen G0 baseline**, therefore the R1 config must use the latter hash.

## Change

- `r1_source_audit.yaml` schema bumped to v2.
- `Z22_BERLIN_GLOSSARY.sha256` changed to the F0.4/G0 rebaseline hash.
- A regression test was added so the frozen G0 glossary identity cannot silently regress.

## Impact

- Scientific decisions F0–F2: **NONE**.
- G0 status: **UNCHANGED / SUPERADO**.
- Source semantics: **UNCHANGED**.
- R1 execution: must use this corrected v2 config.
- Commit `b90bbd2` remains traceable as the initial R1 implementation baseline, but must not be used for the official R1 run.

## Classification

Implementation/configuration alignment issue found before data execution. No raw data were transformed and no R1 result was produced under the incorrect hash.
