# MAIN update — F3.4g-2e Held-out TEST Protocol PREOPEN

If committed after PRE-COMMIT PASS:
- held-out split identity is frozen by F1 manifest SHA-256;
- TEST membership remains household-atomic and seed-bound;
- full split counts are 1238/268/264;
- strict R_min split counts are 1219/263/260;
- TEST outcome files remain unmaterialized;
- 17 Joint metrics are reused unchanged (14 decision, 3 report-only);
- 32 CRN replicates and TEST seed 20261003 are frozen;
- candidate selection and post-TEST tuning are forbidden;
- holdout becomes consumed only after TEST outcome-content I/O;
- TEST outcome rows read remain 0;
- G2 remains NOT_EVALUATED.

Next: implement a commit-bound TEST materialization/evaluation runner PREOPEN with negative-authorization zero-outcome-I/O proof.
