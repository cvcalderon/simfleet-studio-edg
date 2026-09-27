# F3.3c — PRE-CAL Gate v1

F3.3c can pass PreCommit only if:

- parent HEAD is exact F3.3b commit;
- worktree has only the F3.3c overlay;
- overlay checksums are exact;
- 32 stochastic replicates are frozen;
- 1000 paired household bootstraps are frozen;
- 95% percentile CI is frozen;
- CRN seed excludes artifact/candidate/grid;
- draw-index packing is frozen;
- standardized evidence key is unique;
- candidate pairing rejects seed mismatch;
- ISOLATED/PROPAGATED modes remain exact;
- CAL access guard rejects CAL opening;
- TEST access guard rejects TEST opening;
- `cal_rows_read = 0`;
- `test_rows_read = 0`;
- candidate selection remains NONE;
- synthetic-only harness tests pass.

Passing F3.3c PreCommit is necessary but not by itself a TEST-opening decision.

After commit, MAIN may evaluate the complete PRE-CAL entry gate and authorize the first
controlled CAL run. TEST remains sealed.
