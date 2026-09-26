# MAIN update — F3.2a preparation v1

- F3.1 model-design freeze is complete at commit `58bb4183a9557b8b8b069552813db9530cb848b0`.
- F3.2a freezes deterministic TRAIN/CAL materialization before implementation.
- TEST remains sealed and has no materialization output path.
- Synthetic R4 rows are interface compatibility evidence, not fitting rows.
- Eight logical tables per allowed partition preserve task-specific universes and explicit missing-context/backoff states.
- Expected TRAIN anchors: context 2200; participation 2154; count 1791; chain days 1422; chain transitions 4872; time 6103; raw distance 5617; expanded distance 6145.
- Expected CAL support is frozen by row count only; no CAL performance metric has been inspected/tuned in this step.
- Next after freeze: F3.2b implementation of materializer + shared encoders; still no candidate fitting until materialization bundle passes its own audit.
