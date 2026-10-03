# F3.4g-2d — Joint Real-CAL A1 Closure / TEST Eligibility Freeze v1

## Decision

The preserved F3.4g-2c A1 Joint real-CAL execution is formally closed as:

`JOINT_CAL_A1_CLOSED_PASS`.

The Joint gate passed under the frozen F3.4g-1 selected-vs-all-reference
contract.

## Authoritative execution evidence

- exact implementation commit: `beeb79a79e81aaaff3041542c3a9f3c08937e1dc`;
- exactly eight authorized CAL files;
- exactly 6,341 physical CAL rows;
- 10 frozen pipeline artifact slots;
- 32 paired CRN replicates;
- 30,016 generated person-day rows;
- 97,134 generated trip rows;
- candidate selection: `NONE`;
- RunBundle integrity: PASS;
- Joint gate: PASS;
- gate reasons: none;
- structural violations: 0;
- temporal violations: 0;
- NoFutureInformation violations: 0.

## Metric interpretation

The frozen Joint thresholds are **maximum allowed worsening versus the
ALL_REFERENCE pipeline**. They are not absolute goodness-of-fit thresholds.

All 14 decision-driving metrics pass.

Only two decision metrics worsen relative to ALL_REFERENCE:

- `M2-COUNT-01`: +0.006096 versus tolerance +0.10;
- `DIST-P50`: +0.012927 km versus tolerance +0.50 km.

All other decision-driving metrics are equal or improve.

Three report-only metrics remain non-decision evidence:

- `TIME-CIRCULAR-W1`;
- `DIST-MEAN`;
- `M2-DIST-02`.

Therefore the correct claim is:

`selected pipeline does not materially degrade the frozen all-reference
comparator under the preregistered Joint gate`.

The closure does **not** claim that every absolute error is small or that every
individual metric meets an independent absolute target.

## TEST boundary

The Joint primitive returns:

`test_eligible_by_joint_gate = true`.

This is eligibility only.

This freeze explicitly retains:

```text
TEST open authorized = false
TEST rows read = 0
formal G2 = NOT_EVALUATED
```

No held-out TEST file may be opened until a separate TEST protocol is frozen and
MAIN issues an explicit commit-bound authorization.
