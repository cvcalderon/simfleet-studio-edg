# F3.1b — Low-support and deterministic backoff policy v1

## Frozen rule

F2.2 already defines a source cell with fewer than **30 strict-TRAIN rows** as `LOW_N`. F3.1b reuses that definition rather than inventing a second support convention.

For conditional empirical samplers and Markov/n-gram contexts:

1. construct the most specific predeclared conditioning key;
2. compute strict-TRAIN `source_n` before weighted sampling;
3. if `source_n >= 30`, the cell is eligible for direct sampling;
4. if `source_n < 30`, emit a `LOW_N_BACKOFF` audit record and remove exactly one conditioning dimension according to the hierarchy frozen later in F3.1c;
5. repeat until support is sufficient or the declared root model is reached;
6. never create an undeclared pooled cell and never use TEST/CAL outcomes to fill support.

`P_GEW`/`W_GEW` determine probabilities **inside** an eligible cell. They do not transform a low raw source count into high empirical diversity.

Global statistical candidates (regularized logistic/NB GLM) do not use cell backoff for fitting, but sparse categories/levels must be encoded using a TRAIN-only deterministic category policy and remain visible in subgroup diagnostics.
