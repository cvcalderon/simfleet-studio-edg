# F3.4d-2c — Activity Chain MAIN Freeze Decision v1

## Decision

`DG_ACTIVITY_CHAIN::CHAIN_A::CHA2 = MAIN_FROZEN`

This is a formalization of the result produced by the preregistered CAL rules.
No new candidate, feature, threshold, metric, or hyperparameter is introduced
after CAL inspection.

## A1 evidence

The controlled A1 execution completed PASS using exactly 1853 physical CAL rows:
469 person-day context rows, 319 chain-day rows and 1065 chain-transition rows.

The RunBundle checksum audit passed. The post-run verifier initially had one
mechanical JSON serialization defect; that defect was remediated without
modifying the RunBundle, and the same immutable RunBundle then verified PASS
with zero failed checks.

## Primary metric

| Artifact | Weighted next-activity log-loss |
|---|---:|
| CHAIN_REF / REFERENCE | 3.042920920013547 |
| CHAIN_A / CHA1 | 1.3914707267968025 |
| CHAIN_A / CHA2 | **1.3549031390197808** |
| CHAIN_B / CHB1 | 1.5795339318736559 |
| CHAIN_B / CHB2 | 1.7904982627799542 |
| CHAIN_B / CHB3 | 1.86030330835725 |

Within CHAIN_A, CHA2 is the frozen-rule family selection.

## Promotion REF -> CHA2

- point improvement: 1.6880177809937664;
- practical margin: 0.01;
- paired household bootstrap: 1000 replicates;
- CI95: [0.24699909115857205, 3.7193672069888444];
- lower CI bound > 0;
- promotion: PASS.

## Guardrails

REF -> CHA2 passes all three ISOLATED guardrails. The same provisional
selection also passes PROPAGATED guardrails using MAIN_FROZEN PA1 and COUNT_REF
upstream state.

The CHAIN_B candidates do not pass the frozen guardrail requirements against
CHA2, therefore no CHAIN_B promotion is eligible.

## Frozen artifact identity

- artifact: `DG_ACTIVITY_CHAIN::CHAIN_A::CHA2`;
- model SHA-256: `242085ebab9eb5ec8a53ea3b8ffe65c1d1e1fdb660bcacff0ab172d1b5ef1ecf`;
- manifest SHA-256: `337140dd45522a47659603998838a3c869646cbd70961ba874d6f34be555ea73`;
- TRAIN implementation commit:
  `8aa9af765ed9aa2d69fe797c1530c88ae55ed5f4`;
- purpose primitive: `CHAIN_PURPOSE_ATTRIBUTION_V1`;
- purpose artifact SHA-256: `ab42cf42c9568ef4f085f071299fc941d421c42337f353e00870cd05c94f94fb`.

## Boundaries

- Activity Chain is frozen for D_GEN runtime use.
- DG_TIME_SCHEDULE is **not** yet authorized for real-CAL opening.
- TEST remains SEALED.
- Formal G2 remains NOT_EVALUATED.

Next step:
prepare DG_TIME_SCHEDULE CAL evaluation/freeze lane under a separate
authorization sequence.
