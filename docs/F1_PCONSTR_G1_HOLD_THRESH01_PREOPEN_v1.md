# F1-P_CONSTR-G1 HOLD-THRESH-001 PREOPEN v1

Parent: `2b72fce94deae889e85953bdc8c142e91ae6b4a9`.

This PREOPEN resolves the last pre-holdout scientific blocker by freezing a deterministic threshold-transfer rule from the already-frozen CAL materiality tolerances.

It performs no source-partition execution and authorizes no holdout I/O.

After a successful commit and synchronization:

- `HOLD-MREAL-001 = RESOLVED_FROZEN`;
- `HOLD-THRESH-001 = RESOLVED_FROZEN`;
- `1000A-1035 = UNACQUIRED / UNREAD / UNAUTHORIZED`;
- the next task is a separate commit-bound holdout authorization PREOPEN.
