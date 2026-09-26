# F3.2c — Modeling environment extension v1

## Purpose

Extend the accepted Python 3.12 `py312-edg` environment with the libraries required by the already-frozen F3.1/F3.2 model families. This step changes software availability only; it does not alter candidate families, features, objectives, CAL rules, thresholds, TEST sealing, or the accepted F3.2b materialized data.

## Declared dependencies

- `scipy>=1.16,<2`
- `scikit-learn>=1.7,<2`
- `statsmodels>=0.14.5,<1`
- `lightgbm>=4.6,<5`

The install command is intentionally derived from `pyproject.toml`:

```bash
python -m pip install -e ".[modeling]"
```

Exact resolved versions are evidence and must be captured after installation rather than guessed in advance.

## Scientific mapping

- DG_PARTICIPATION A: weighted regularized logistic Bernoulli -> scikit-learn implementation.
- DG_PARTICIPATION B: probabilistic binary LightGBM -> LightGBM implementation.
- DG_TRIP_COUNT A later requires a Negative Binomial GLM -> statsmodels.
- SciPy supports the numerical/statistical stack.

No unavailable frozen family may be silently replaced by another algorithm.

## Generated-output hygiene

F3.2b produced `artifacts/model_data/F3_2a_training_data_v1`. It is a generated scientific artifact, not source code. `/artifacts/model_data/*` is therefore ignored in the repository, exactly like `/artifacts/runs/*` and `/artifacts/reports/*`.

`/artifacts/environment/*` is also reserved for generated environment snapshots. Those snapshots are audited/archived separately; they are not source-controlled as runtime source files.

The already accepted F3.2b archive/checksums remain the provenance authority for the materialized dataset.
