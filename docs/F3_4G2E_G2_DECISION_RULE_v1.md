# F3.4g-2e — Formal G2 decision rule v1

Let the authorized held-out TEST execution produce:

- execution integrity status `E`;
- structural violations `V_s`;
- temporal violations `V_t`;
- NoFutureInformation violations `V_f`;
- 14 frozen decision metric outcomes `M_1 ... M_14`;
- frozen-artifact witness `A`;
- post-TEST design-change witness `D`.

Then:

```text
G2 = PASS
iff
E = PASS
and V_s = 0
and V_t = 0
and V_f = 0
and all(M_i = PASS)
and A = true
and D = false.
```

If execution integrity is PASS but any decision condition fails:

```text
G2 = FAIL.
```

Operational failures do not become scientific FAIL automatically. Their
handling depends on whether TEST content was already opened.

There is no composite score and no compensatory averaging across decision
metrics.
