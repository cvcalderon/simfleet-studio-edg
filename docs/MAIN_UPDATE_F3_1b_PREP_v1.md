# MAIN update — F3.1b preparation v1

Entry parent: `f12ffa66deccc0888bc4f97d2bab5a89b2881fd0` (F3.1a frozen).

F3.1b freezes a candidate slate for the five D_GEN components. It does not train models and does not open TEST.

Key decisions:
- interpretable/empirical Candidate A plus flexible Challenger B;
- LLM full-day schedule generation remains outside core D_GEN v1;
- F2.2 `LOW_N < 30` rule becomes the explicit backoff trigger;
- timing output is a planned schedule prior, not pre-mode executed route time;
- CAL may select candidates only after F3.1c freezes metrics/thresholds;
- named deterministic RNG namespaces/canonical candidate ordering required.

Next on successful VM validation: freeze F3.1b commit, then open F3.1c fitting/calibration/acceptance protocol.
