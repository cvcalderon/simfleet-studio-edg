# SimFleet-EDG — F3.1b D_GEN candidate model-family freeze v1

**Parent:** F3.1a commit `f12ffa66deccc0888bc4f97d2bab5a89b2881fd0`  
**Status:** candidate slate frozen; no model has been trained; TEST sealed.

## 1. Why this is a candidate-slate freeze, not a winner declaration

The strict-TRAIN evidence is modest at person-day level (participation `n=2154`; positive-count/mobile `n=1791`; full-functional sequence `n=1422`) and larger at trip level (time `n=6103`; raw distance `n=5617`). F3.1b therefore freezes a small auditable candidate set and lets CAL decide only after F3.1c freezes the evaluation protocol. A more complex model is not promoted merely because it is more flexible.

## 2. Frozen core slate

| Component | Candidate A | Challenger B | Reference |
|---|---|---|---|
| Participation | weighted regularized logistic Bernoulli | LightGBM binary probabilistic | weighted empirical Bernoulli |
| Positive trip count | NB GLM on `K-1` | weighted conditional empirical PMF | unconditional positive-count PMF |
| Activity chain | terminal-aware variable-order Markov/n-gram | regularized multinomial next-activity | first-order transition matrix |
| Time | weighted conditional empirical temporal kernel | quantile gradient boosting | departure-hour empirical distribution |
| Distance prior | weighted conditional inverse-ECDF on raw `wegkm` | quantile gradient boosting | unconditional raw `wegkm` ECDF |

Candidate A is the default implementation order, **not** a predetermined empirical winner.

## 3. Why the count model uses `K-1`

Participation already decides `NoTrip` versus `TripDay`. For a generated trip day, `K>=1`. Modelling `Y=K-1>=0` with a Negative-Binomial GLM avoids introducing a second zero/hurdle process and preserves the F3.1a DAG. Runtime draws use `K=1+Y`.

## 4. Why chain/time/distance retain empirical candidates

The project needs a strong empirical D_GEN reference before testing richer LLM behaviour downstream. Component-level empirical sampling does **not** copy a whole donor day as D_MATCH does: chain transitions, timing and distance are sampled from task-specific strict-TRAIN evidence with explicit conditioning/backoff. This reduces whole-diary selection dependence while preserving multimodal empirical distributions.

## 5. LLM boundary relative to GTA

GTA demonstrates a different design choice: its LLM generates a structured full-day activity schedule from persona/date/context before concrete trip planning. SimFleet-EDG deliberately does not make that the core D_GEN v1 because the study intends to isolate the later incremental contribution of LLM-based behavioural reasoning. An LLM schedule generator may be studied only as a separately labelled experimental ablation after the empirical core is established.

## 6. Timing semantic guardrail

Observed trip arrival/duration partly reflects the route and mode that actually occurred. D_GEN therefore must not reinterpret `duration_from_clock_min` as a physical route-time prediction before M5. In the M2 output it is a **planned temporal schedule quantity/prior** derived from the generated clock states. Realised route/service duration belongs downstream and may differ.

This is a semantic refinement of the F3.1a output, not permission to feed mode or routing evidence upstream.

## 7. Low support

The F2.2 convention is retained: strict-TRAIN `source_n < 30` is `LOW_N`. Conditional empirical/Markov contexts must emit an audit flag and deterministically back off. No silent pooling is allowed.

## 8. What remains for F3.1c

F3.1c freezes the exact feature subset per candidate, preprocessing, hyperparameter/search spaces, deterministic backoff hierarchy, CAL promotion metrics and numeric thresholds, probability calibration strategy, count-tail policy and quantile-grid reconstruction. Only after that freeze may fitting begin.
