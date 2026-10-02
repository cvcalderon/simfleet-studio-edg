# MAIN update — F3.4f-2b A1 verifier remediation

A1 scientific execution completed and proposed `DIST_REF_REFERENCE` under the
frozen CAL rules. The subsequent RunBundle verifier crashed only because a
`numpy.bool_` value was passed to `json.dumps`.

Remediation scope is verifier-only plus a regression test. No CAL rerun is
authorized or required. The existing A1 RunBundle must be preserved and later
verified unchanged after the remediation commit is synchronized.
