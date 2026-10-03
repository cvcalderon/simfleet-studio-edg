# MAIN update — F3.4g-2b Joint Real-CAL Authorization PREOPEN

If committed after PRE-COMMIT PASS:

- the external commit-bound authorization boundary is frozen;
- positive authorization must occur before any CAL content I/O;
- positive authorization must occur before output staging;
- the tracked authorization template remains negative;
- no Joint CAL row has been read;
- the real Joint runner is still not authorized to execute;
- TEST remains sealed;
- G2 remains NOT_EVALUATED.

Next step: F3.4g-2c Joint real-CAL runner implementation PREOPEN. That runner
must reuse the already frozen F3.4g-1 metric matrix and component denominator
semantics.
