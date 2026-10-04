# F1-P_CONSTR-IMPL-02 — implementation note

## Scale projection

`EXACT_L1_MODULAR_ROUNDING_V1` minimizes the exact integer numerator

`sum |D*x_i - N*f_i|`,

where `D=3,532,081`, `N` is the requested scale and `f_i` is the frozen IMPL-01 full-scale cell target.

Exact Bezirk totals are Hamilton/largest-remainder integerizations. Structural zeros remain zero. Aggregate person totals for household sizes 1..5 must be divisible by the exact household size.

No MILP is required. With Bezirk totals fixed, each cell can only need a floor/ceil decision. The implementation performs dynamic programming over the six household-size groups and therefore obtains the exact L1 optimum while enforcing the modular constraints. `CANONICAL_WEIGHTED_INCREMENT_V1` resolves primary-objective ties deterministically.

## 6+ structural completion

`H6_COMPLETION_V1` derives the full-scale household-count prior from `5000H-1001 × rho_multi_2_5`, with Berlin total 28,343. The prior is model-derived structural evidence, **not** a source-hard target.

At each S/M/L scale the prior is largest-remainder scaled subject to `6*H6_b <= P6_b`. Individual top-coded sizes are completed by `UNIFORM_WEAK_COMPOSITION_V1` using master seed `20261004` and a SHA256-derived per-scale/per-Bezirk substream.

This phase produces only latent household sizes and provenance. TRAIN donor/template realization is explicitly deferred to IMPL-03.
