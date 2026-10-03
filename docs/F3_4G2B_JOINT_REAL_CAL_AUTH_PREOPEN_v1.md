# F3.4g-2b — Joint Real-CAL Authorization Boundary PREOPEN v1

## Purpose

Freeze the irreversible authorization boundary that must exist before the final
Joint selected-vs-all-reference CAL runner is allowed to open any empirical CAL
file.

This phase does **not** implement scientific CAL metrics and does not read CAL
content. That implementation is deliberately deferred to F3.4g-2c so it can
reuse the already accepted component evaluation semantics rather than inventing
new schema assumptions here.

## Entry state

- F3.4g-1 Joint CAL contract: authoritative.
- F3.4g-2a synthetic end-to-end orchestration: authoritative PASS.
- all five selected D_GEN components: MAIN_FROZEN.
- CAL rows read in this phase: 0.
- TEST rows read: 0.

## External authorization rule

A positive Joint real-CAL execution authorization:

1. must be external to Git;
2. must be tied to the exact implementation commit;
3. must require `main`;
4. must require `HEAD == origin/main`;
5. must require a clean repository;
6. must list exactly the eight allowed CAL files;
7. must authorize both CAL opening and Joint gate evaluation;
8. must keep TEST closed and G2 unevaluated.

The positive authorization must be validated **before**:

- opening any CAL path for content;
- creating a `.partial` or final RunBundle directory.

## Failure rule

Invalid or missing authorization is a zero-I/O failure:

```text
CAL files opened = []
CAL rows read = 0
staging created = false
```

If a later F3.4g-2c execution fails after valid authorization and staging has
begun, the `.partial` evidence is preserved and the same authorization must not
be reused. MAIN review and a new commit-bound authorization are required.

## Boundary after F3.4g-2b

```text
Joint real CAL = NOT_AUTHORIZED
Joint gate = NOT_EVALUATED
TEST = SEALED
G2 = NOT_EVALUATED
```
