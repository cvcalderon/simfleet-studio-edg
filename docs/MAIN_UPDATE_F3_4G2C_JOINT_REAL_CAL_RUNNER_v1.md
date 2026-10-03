# MAIN update — F3.4g-2c Joint Real-CAL Runner PREOPEN

If PRE-COMMIT passes and the overlay is committed:

- the final Joint real-CAL runner exists;
- authorization validation precedes CAL I/O and staging;
- all eight CAL file hashes and row counts are frozen;
- the runner evaluates the F3.4g-1 Joint metric matrix without a composite score;
- scientific Joint PASS/FAIL is separated from execution PASS/FAIL;
- TEST remains sealed;
- G2 remains NOT_EVALUATED.

Only after the exact implementation commit is pushed and synchronized may MAIN
issue an external A1 Joint real-CAL authorization bound to that commit.
