# F3.4e-2b-A6 Closure

`A6 = PASS_VALIDATED_AND_PROPOSED`

The controlled real-CAL A6 execution is the authoritative selection evidence for
`DG_TIME_SCHEDULE`. Its immutable RunBundle is retained at:

`$HOME/simfleet-edg-runs/F3_4e2b_DG_TIME_SCHEDULE_REAL_CAL_A6_v1`

A6 executed at implementation commit `e7207c81b803444fdaae78bd3ec489a1021fb96f` and passed:

- controlled CAL runner status: PASS;
- RunBundle checksum audit: PASS;
- RunBundle verifier: PASS with zero failed checks;
- candidate selection state: `PROPOSED_BY_FROZEN_CAL_RULES_AWAITING_MAIN_FREEZE`;
- proposed selected artifact: `TIME_B_TB2`;
- propagated conjunctive temporal guardrail: PASS;
- TEST rows read: 0;
- formal G2: NOT_EVALUATED.

A6 is not rerun during F3.4e-2c. The MAIN freeze only formalizes its
preregistered result.
