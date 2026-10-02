# F3.4f-2b A1 — RunBundle verifier remediation v1

## Classification

`VERIFIER_ONLY_REMEDIATION_AFTER_CONTROLLED_CAL`

The controlled A1 execution completed successfully at implementation commit
`1530cac0b4d634eb064bc46d5fb7ee429518d208` and produced its RunBundle before
the verifier failed.

The failure occurs only while JSON-serializing the verifier report:
`pandas.Series.eq(...).all()` returns a NumPy boolean scalar, which the standard
`json` encoder does not serialize.

## Authorized correction

Only the verifier representation is corrected:

```python
bool(validation["status"].eq("PASS").all())
```

No metric, threshold, candidate score, selection rule, CAL input, stochastic
seed, model artifact, or generated result is modified.

## Re-execution policy

- DO NOT rerun the controlled CAL computation.
- DO NOT reopen CAL source CSV files for this remediation.
- Preserve the existing A1 RunBundle produced by implementation commit
  `1530cac0b4d634eb064bc46d5fb7ee429518d208`.
- After this fix is committed and synchronized, run the corrected verifier on
  that existing RunBundle and package it unchanged.
- Record the verifier commit separately from the implementation commit.

## Boundaries

- Joint CAL gate remains `NOT_AUTHORIZED`.
- TEST remains `SEALED` and `test_rows_read = 0`.
- Formal G2 remains `NOT_EVALUATED`.
- The proposed artifact remains a CAL proposal awaiting MAIN freeze; this
  remediation does not authorize downstream use.
