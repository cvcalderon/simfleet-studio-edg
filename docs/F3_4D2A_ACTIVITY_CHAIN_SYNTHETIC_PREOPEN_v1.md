# F3.4d-2a — Activity Chain Synthetic/TRAIN PRE-OPEN

## Purpose

Validate the Activity Chain CAL evaluation plumbing before any CAL row is opened.

This phase is deliberately reversible:
- it may read the already accepted F3.2e TRAIN-fit RunBundle;
- it may load/rehash the six TRAIN model artifacts and their manifests;
- it executes only a synthetic evaluation fixture;
- it does not open the F3.2a CALIBRATION directory;
- it does not select or promote a candidate.

## What the dry-run exercises

The synthetic runner verifies:
- exact candidate universe and artifact hashes;
- weighted next-activity log-loss;
- categorical TVD;
- return-home-share absolute error;
- exact K transitions / K+1 states;
- deterministic SHA256 seed derivation;
- common-random-number semantics;
- paired household bootstrap mechanics;
- RunBundle checksums and evidence manifests.

The synthetic metric values are plumbing evidence only. They are not scientific
CAL evidence and must never be used to select a model.

## Frozen TRAIN artifact hashes

The six model/model-manifest hashes come from the accepted F3.2e
`model_artifact_index.csv`. Any mismatch blocks PRE-OPEN.

## Boundary

Successful F3.4d-2a does **not** authorize real CAL. It only permits MAIN to prepare
the next real-CAL PRE-OPEN/authorization step.

TEST remains sealed and G2 remains NOT_EVALUATED.
