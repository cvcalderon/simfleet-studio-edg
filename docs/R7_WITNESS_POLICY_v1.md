# R7 historical witness policy v1

The historical F2.2 package is used to verify reproducibility, not as a substitute
for recomputation.

Computed outputs:

- reference populations;
- distribution detail;
- global metrics;
- conditional metrics;
- selection-bias audit;
- validation;
- manifest.

Frozen contract/interpretive records copied after validation:

- metric protocol;
- diagnostic issues;
- diagnostic validation report;
- traceability entry.

Historical comparison:

- ten artifacts: `BYTE_EXACT`;
- `simfleet_edg_F2_2_global_metrics_v1.csv`: `NUMERIC_EQUIVALENT`, `atol=1e-12`.

The numeric-equivalence exception is intentional and explicit. It must not be
reported as byte-exact reproduction.
