# F3.2b local dry-run v1

Preparation environment used the frozen source bytes available to the build workspace.

Results:

```text
focused tests                    8/8 PASS
Python compile                   PASS
source hash validation          13/13 PASS
frozen row-count validation     16/16 PASS
TEST materialized               false
second materialization          23/23 files byte-identical
```

Observed contract diagnostics:

```text
raw distance missing valid time context
  TRAIN = 32
  CAL   = 11

raw distance unresolved transition context
  TRAIN = 217
  CAL   = 27
```

These rows are retained as required by F3.2a; they are not complete-case dropped.

Ruff and the repository-wide regression suite must be confirmed in the official VM. The reconstructed build workspace is not the authoritative Git checkout for those two gates.
