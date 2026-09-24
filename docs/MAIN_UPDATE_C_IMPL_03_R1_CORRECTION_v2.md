# MAIN update — C-IMPL-03 / R1 correction v2

The R1 implementation passed tests and precheck at commit `b90bbd2`, but cross-checking against the final F0.4/G0 freeze detected one stale expected checksum: the Zensus glossary still referenced its historical F0.1 hash. F0.4 had explicitly rebaselined the validated current glossary copy.

A v2 implementation correction updates the R1 expected glossary SHA-256 to the frozen G0 value and adds a regression test. No scientific rule, source semantics, gate status, or F0–F2 result changes. No official R1 data run occurred before this correction.

Status until v2 is committed and validated: `C-IMPL-03 = MODIFY`.
After v2 tests/Ruff/verifier pass on a clean synchronized commit: `C-IMPL-03 = SUPERADO`, then stage raw sources and execute R1.
