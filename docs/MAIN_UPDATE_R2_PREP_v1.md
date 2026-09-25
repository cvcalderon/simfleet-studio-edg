# MAIN update — R2 preparation v1

R0 and R1 are closed. R2 is the current reproduction rung.

The R2 implementation reconstructs F0.2c eligibility and F1.1 household splitting from R1-verified MiD raw bytes. The frozen F1.1 split algorithm and witness hash are encoded explicitly; no population generation, fitting, CALIBRATION tuning or TEST evaluation is performed.

Acceptance requires all R2 validation checks PASS, including exact `1770 -> 1763 -> 1742`, exact split counts, exact frozen split-manifest SHA-256, exact descendant inheritance counts, and non-empty 22 age×sex support cells in every partition with the frozen minima.

G1 remains open. Passing R2 only proves PRE-F3 reproduction of eligibility/split evidence.
