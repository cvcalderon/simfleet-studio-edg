# F3.1b — TRAIN/CAL/TEST role for the candidate slate v1

- **TRAIN**: fit every frozen candidate, construct empirical distributions, choose TRAIN-internal preprocessing and estimate parameters.
- **CALIBRATION**: compare the already-declared candidates, choose hyperparameters/backoff sensitivity and, when needed, probability/distribution calibration. Exact metrics and promotion thresholds are frozen in F3.1c **before** CAL is opened for model-family decisions.
- **TEST**: remains sealed. It cannot select model family, thresholds, features, backoff levels, quantile grids or hyperparameters.

No candidate may be added after CAL inspection without a new design version/change record. If a new candidate is introduced, previous CAL results cannot be reused as if the candidate had been preregistered.
