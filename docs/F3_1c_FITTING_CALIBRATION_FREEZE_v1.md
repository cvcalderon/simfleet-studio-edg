# F3.1c — D_GEN fitting and CAL protocol freeze v1

## Frozen outcome

F3.1c does **not** train models. It preregisters exactly how the already-frozen F3.1b candidate slate will be fitted on TRAIN and compared on CAL.

### Feature policy

Candidate A and B for the same component receive the same semantic feature subset. The core v1 deliberately excludes employment participation (redundant with primary activity), fine-grained home geography, holiday and generic scenario-known flags from the candidate matrices; these remain allowed by F3.1a but require a later explicit ablation/change record.

No source mobility outcome, survey weight, technical/source identifier, downstream destination/mode/route or execution outcome is a behavioral feature.

### Model-selection policy

The final selected component may be the reference baseline, A, or B. A/B are not entitled to promotion merely because they are more sophisticated. Promotion is lexicographic and paired-bootstrap guarded; ties resolve toward lower complexity.

### Count tail

Participation owns the zero process. Trip count therefore models positive K only. `COUNT_A` fits `Y=K-1` and generates from the NB2 distribution **truncated and renormalized** to the strict-TRAIN support `1..K_MAX_TRAIN`; it is never post-hoc clipped.

### Timing semantics

Observed source arrival/duration can be fitting evidence for a **planned transition-duration prior**, but the generated value is not asserted to be executed route travel time. Physical travel duration remains downstream of M3/M5/execution. This prevents D_GEN from silently pretending that a mode-conditioned physical duration is known before mode choice.

### Distance semantics

Primary distance evidence remains raw `wegkm`. `wegkm_imp` is sensitivity only and `km_routing` is forbidden. Generated distance is a path-length prior for M3, not exact Euclidean OD separation.

### CAL and TEST

CAL may choose only preregistered hyperparameters/candidates. TEST remains sealed until the joint CAL gate passes and selected artifact identities are frozen. That later authorization is still **not** formal G2 closure.
