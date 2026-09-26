# MAIN update — F3.2e DG_ACTIVITY_CHAIN prep v1

F3.2d trip-count TRAIN fitting is closed/SUPERADO. F3.2e opens the TRAIN-only implementation lane for `DG_ACTIVITY_CHAIN`.

Authoritative F3.2a fitting inputs are 1422 full-functional TRAIN mobile days and 4872 materialized TRAIN transitions. The earlier F3.1b descriptive count of 5812 transitions is not the implementation row-count contract; F3.2a froze 4872 eligible transitions.

Frozen candidate slate: `CHAIN_REF`, `CHAIN_A/CHA1..CHA2`, `CHAIN_B/CHB1..CHB3`. `CHAIN_A` implements literal `CHAIN_BACKOFF_V1` with raw support threshold `source_n>=30` and Dirichlet alpha `.1/1`. `CHAIN_B` implements the frozen multinomial next-activity challenger with L2 `.1/1/10` and the same semantic `CHAIN_FEATURES_V1` inputs.

For generated K, the future runtime chain must emit exactly K transitions / K+1 activity states. Return-home is learned/generated and is never universally forced. Same-transition source purpose and future source activities are not predictors.

This overlay trains nothing until implementation is committed. CAL scoring/selection remains disabled and TEST remains sealed. Formal G1 remains OPEN; formal G2 remains NOT_EVALUATED.
