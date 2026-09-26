# MAIN update — F3.1c preparation v1

Parent freeze commit: `ce99ff2f175fcc2df34cca3607754b4de9c4605d`.

F3.1c preregisters feature subsets, fit objectives, hyperparameter grids, deterministic backoff, CAL promotion margins/guardrails, stochastic replication, household bootstrap, seed policy and pre-TEST joint gate. It trains nothing and opens no TEST data.

If VM quality gates pass, commit the package before any D_GEN fitting. The next implementation phase should consume this contract literally; changing features/candidates/margins after CAL inspection requires a new design version/change record.
