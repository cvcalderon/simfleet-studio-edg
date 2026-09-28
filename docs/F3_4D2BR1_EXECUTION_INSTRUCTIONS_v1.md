# F3.4d-2b-R1 execution instructions

TRAIN-only. Do not open CALIBRATION or TEST.

After applying the overlay and verifying static checksums:

```bash
python -m simfleet_edg.repro.f3_4d2br1_purpose_attribution_fit   --config configs/f3/f3_4d2br1_activity_chain_precal_remediation_v1.yaml   --artifact-output configs/f3/f3_4d2br1_purpose_attribution_artifact_v1.json   --witness-output docs/F3_4D2BR1_TRAIN_PURPOSE_WITNESS_v1.json
```

Then run focused/full tests and:
`python scripts/verify_f3_4d2br1_remediation.py`

Stop before staging/commit.
