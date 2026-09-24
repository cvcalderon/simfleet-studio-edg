# C-IMPL-03 / R1 — provenance fix v3

The R1 implementation is unchanged. Only the source contract is amended after the first official R1 run exposed a provenance inconsistency in the Zensus glossary.

Changes:

- `r1_source_audit.yaml` schema -> v3.
- `Z22_BERLIN_GLOSSARY.sha256` -> reproducible official/F0.1 hash `a4f3e588...`.
- `ebd661...` retained explicitly as `superseded_local_copy_sha256`.
- regression test updated to require both identities in their correct roles.

The failed run `R1_source_audit_v1` must not be deleted or overwritten.
