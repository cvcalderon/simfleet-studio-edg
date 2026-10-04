# F1-P_CONSTR-IMPL-02 — PREOPEN

Status: `AUTHORIZED_FOR_PREOPEN_IMPLEMENTATION_ONLY`.

Parent: `6ca6a2fd1f577433237fce3cca8763c84d8f68fe`.

## Scope

IMPL-02 implements only:

1. exact S/M/L scale projection of the frozen full person-domain cube;
2. the structural `H6_COMPLETION_V1` branch: scale-specific 6+ household counts and latent 6/7/8/... household sizes.

It does **not** materialize TRAIN donor households/persons. Donor realization is deferred to IMPL-03, where the common 6+ structural branch is used identically by P_TRS, HD_U and HD_W.

## Frozen boundaries

- CAL: unread;
- MiD TEST: not read by IMPL-02; globally it remains consumed by G2 and must not be reopened;
- `1000A-1035`: unread;
- F3: untouched;
- PLR allocation: deferred;
- HD_U / HD_W construction: deferred;
- G1: OPEN;
- G2: PASS / CLOSED / DO NOT REOPEN.
