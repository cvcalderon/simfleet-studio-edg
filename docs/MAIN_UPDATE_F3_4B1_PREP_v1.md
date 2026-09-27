# MAIN update — F3.4b-1 prepared

F3.4b-1 implements a Participation runner dry-run that is deliberately incapable of reading CAL/TEST. It validates the eight frozen TRAIN artifacts on synthetic context and executes synthetic metric/bootstrap/selection plumbing into a RunBundle.

Expected invariant at closure:

```text
CAL rows read        = 0
TEST rows read       = 0
candidate selection  = NONE
TEST                 = SEALED
formal G2            = NOT_EVALUATED
```

Only after MAIN closes F3.4b-1 may F3.4b-2 introduce the controlled real CAL reader for `DG_PARTICIPATION`.
