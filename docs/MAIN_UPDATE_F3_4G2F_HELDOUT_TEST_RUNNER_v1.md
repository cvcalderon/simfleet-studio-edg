# MAIN update — F3.4g-2f Held-out TEST Runner PREOPEN

If PRE-COMMIT passes and the overlay is committed:

- TEST materialization/evaluation code exists;
- historical F3.2a TRAIN/CAL contract remains unchanged;
- TEST membership is frozen to the 260 strict R_min TEST households;
- TRAIN vocabulary is reused without TEST fitting;
- TEST seed 20261003 is implemented independently from the CAL seed;
- authorization precedes staging and source-content I/O;
- a consumption marker precedes first source-content read;
- 17 frozen metrics and formal G2 PASS/FAIL are implemented;
- tracked authorization remains negative;
- TEST outcome rows read remain 0;
- TEST remains unconsumed;
- G2 remains NOT_EVALUATED.

Only after the exact runner commit is pushed and synchronized may MAIN issue
the single-use TEST authorization.
