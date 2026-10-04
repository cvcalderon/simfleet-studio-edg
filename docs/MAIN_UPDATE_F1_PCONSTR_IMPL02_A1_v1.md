# MAIN UPDATE — F1-P_CONSTR-IMPL-02 A1

## Decision

`F1-P_CONSTR-IMPL-02 A1 = ACCEPTED FOR MAIN FREEZE`

## Authoritative lineage

- IMPL-01 freeze commit: `6ca6a2fd1f577433237fce3cca8763c84d8f68fe`
- IMPL-02 implementation commit: `b60017b8233856fa365bc63d4ddca9aa47e14566`
- Official IMPL-02 RunBundle SHA256: `3a22dcf88dfbd83271d8b0b65d4d3c5590431bcf8ac269fddf713c4364474b81`

## Frozen outputs

- S = 10,000 persons; P6=685; H6=80.
- M = 100,000 persons; P6=6,873; H6=802.
- L = 1,000,000 persons; P6=68,711; H6=8,024.
- Full-scale H6 structural target = 28,343.
- All Bezirk targets exact.
- Structural-zero violations = 0.
- Size 1..5 divisibility violations = 0.
- H6 household IDs unique and all generated sizes >=6.
- Donor materialization remains deferred.

## Semantic guardrail

`242,676` is the full-scale reconciled `6+` person count used for projection. The raw published 1000A-1029 `6+` margin `242,700` MUST NOT be substituted post hoc.

## Gates

- G1 = OPEN
- G2 = PASS / CLOSED / DO NOT REOPEN

## Next authorized task after freeze commit

`F1-P_CONSTR-IMPL-03_PREOPEN`
