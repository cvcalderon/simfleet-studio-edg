# F3.4d-2b-A1 — RunBundle verifier mechanical remediation v1

## Scope

This remediation changes only the presentation/serialization layer of the
post-run verifier.

Observed failure after a successful controlled CAL run:

`TypeError: Object of type bool is not JSON serializable`

Root cause:
`pandas.Series.eq(...).all()` can return a NumPy boolean scalar. The verifier
stored that scalar directly in the `checks` mapping and `json.dumps()` rejected
it.

## Exact change

Before:

```python
"validation_all_pass": not validation.empty and validation["status"].eq("PASS").all(),
```

After:

```python
"validation_all_pass": bool(
    not validation.empty and validation["status"].eq("PASS").all()
),
```

No RunBundle byte is modified. No CAL input is reopened. No candidate metric,
guardrail, bootstrap interval, promotion decision, threshold, or selection rule
is changed.

The existing A1 RunBundle MUST be preserved and the patched verifier MUST be
rerun against that same immutable RunBundle.

TEST remains sealed. DG_TIME_SCHEDULE remains unauthorized. G2 remains
NOT_EVALUATED.
