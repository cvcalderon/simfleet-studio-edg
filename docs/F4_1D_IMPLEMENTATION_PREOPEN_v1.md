# SimFleet-EDG — F4.1d Implementation PREOPEN v1

**Phase:** `F4.1d — Production D_GEN Runtime Binding`  
**Parent:** `eebccc7a43eb7c1ef2661da3f357c0e5b01e72ef`  
**State:** `IMPLEMENTATION_PREOPEN`

## Authorized implementation

The implementation binds accepted `P_CONSTR_RMIN_V2_HD_U / M` runtime identities and explicit
`ScenarioDayContext` to the already-frozen selected D_GEN pipeline:

```text
PA1 → COUNT_REF → CHA2 → TIME_B_TB2 → DIST_REF_REFERENCE
```

No fitting, calibration, selection, donor-day substitution, destination assignment, or spatial
candidate execution is authorized.

## Runtime identity and context

`source_household_id` and `source_person_id` in the backward-compatible F4.1b day/trip schema
carry accepted generated M1 IDs. `source_weekday` and `source_season` are aliases of the caller
supplied scenario weekday/season. `6_PLUS` is preserved exactly and may only be handled by the
frozen adapter unseen/backoff policy.

## Quality and execution boundary

Before commit: focused tests, scoped Ruff, repository Ruff differential, scoped mypy, repository
mypy differential, full regression, PREOPEN verifier, and exact-scope audit must pass. The worker
then stops. Commit and push are performed manually from PyCharm.

Only after that push may the deterministic 512-person smoke execute, twice, with exact canonical
output SHA-256 equality. The smoke is engineering evidence and is not downstream-authorized.

Forbidden throughout F4.1d: CAL reads, MiD TEST reads, G1/G2 reopen, model changes, full 100k
production D_GEN realization, destination assignment, S_NEAR, S_DIST, S_ATTR, G3, mode, routing,
and terminal push.
