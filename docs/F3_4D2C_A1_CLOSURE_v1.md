# F3.4d-2b-A1 Closure

`A1 = PASS_VALIDATED`

The original controlled real-CAL run is retained and is not rerun.

The post-run verifier serialization failure was a mechanical presentation bug:
a NumPy boolean scalar entered `json.dumps`. The verifier was patched with a
Python `bool(...)` normalization only. The same immutable RunBundle then passed
all verifier checks.

No CAL data were reopened by the remediation, no RunBundle evidence was
modified, and no selection rule changed.
