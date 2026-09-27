# MAIN UPDATE — F3.3d PRE-CAL Entry Gate

Status at overlay creation:

`PRECOMMIT_PENDING`

Required parent:

`a4f650165f6e9f89b2d72fededec559a81bd30f8`

The gate reads only committed PRE-CAL contracts, frozen TRAIN artifact identities,
Git metadata and regression evidence. It must not read CAL or TEST.

A successful gate authorizes the next controlled CAL evaluation run only.

TEST remains SEALED and formal G2 remains NOT_EVALUATED.
