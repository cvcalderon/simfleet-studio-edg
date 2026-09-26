# R7 lint fix v2

Scope: mechanical static-quality corrections only. No scientific, metric, threshold, input, witness, or output-contract changes.

Changes in `src/simfleet_edg/common/diagnostic_metrics.py`:

1. `Iterable` imported from `collections.abc` instead of `typing` (`UP035`).
2. Ambiguous local variable `l` renamed to `left_aligned`, paired with `right_aligned` (`E741`).
3. Removed unused local `part_groups` assignment (`F841`).

Expected effect: Ruff gate becomes PASS while numerical behavior remains unchanged.
