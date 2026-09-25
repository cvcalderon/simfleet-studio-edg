# R4 implementation note — `P_TRS_EXP_V1_M`

## Scope

R4 reproduces the frozen F1.3b M-scale PRE-G1 population. It is a controlled
scale change from S=10,000 to M=100,000 persons. It does not change donor
eligibility, weighting, seeds, resource semantics, geography logic or the G1
status.

Frozen generation semantics:

- strict TRAIN donor pool: 1,219 households;
- whole-household sampling with replacement;
- probability proportional to `H_GEW`;
- exact-person target algorithm `WEIGHTED_WHOLE_HOUSEHOLD_EXACT_PERSON_TARGET_V1`;
- generation seed `20260922`;
- PLR household-total largest-remainder allocation;
- zone seed `20260923`;
- no CALIBRATION/TEST donors;
- no downstream mobility outcomes in M1.

## Historical witnesses recovered

Primary snapshot:

- persons: 100,000;
- households: 56,365;
- resource relations: 639,661;
- linked Personen: 89,459;
- roster-only persons: 10,541;
- snapshot SHA-256: `a3a9be46286d150e1032d1872ca0e47775407ee14835980f0d5a71be92c57f7d`.

Donor reuse:

- unique donors used: 1,213 / 1,219;
- maximum replicas: 203;
- median replicas among used donors: 39.0.

Structural validation is the frozen 23-check `PTRS-M-001..023` suite.

## Exact primary bytes

R4 requires exact reproduction of the three primary CSVs:

- households: `a7aed5fdfa1e55ec94781733b3144d5ffab8d9051b2663e5eb6672939948ee42`;
- persons: `e75c5c2ba417ddbd87bc074796f6052675cc325c1cec1f671fb8faf288edf70c`;
- resources: `c4f6ecdf7556a66e0faa5eba7704d7cc54c99fbf9387082c2a4c599f7f390842`.

The local reverse-reproduction test confirmed all three hashes exactly.

## Scale-specific generated ID width

The historical S and M artifacts use different zero-padding widths:

```text
S household/person draw id: 6 digits
S relation id:              7 digits

M household/person draw id: 7 digits
M relation id:              8 digits
```

Example:

```text
S: HH_P_TRS_EXP_V1_S_000001
M: HH_P_TRS_EXP_V1_M_0000001

S: REL_S_0000001
M: REL_M_00000001
```

This is a serialization/identity-format compatibility rule. It does not change
sampling or scientific semantics. `population_materializer.py` now preserves the
historical format for both S and M; the existing R3 tests remain unchanged.

## Exact compact witnesses

The following are required byte-exact:

- frozen M compact manifest;
- M structural validation CSV;
- M donor reuse CSV;
- M zone allocation CSV.

The historical compact M manifest embeds historical F1.3b performance values.
R4 recreates that historical artifact only as a frozen witness. Current-environment
performance is recorded separately and must not be substituted into that compact
reference artifact.

## Numeric/report-only witnesses

Preservation and S→M stability metrics are floating-point diagnostics. R4 checks
them with absolute tolerance `1e-12`; byte equality is not required.

Historical M TVD:

```text
household_size          0.0025500703113384
age_infr_class          0.0047791635771124
sex                     0.0005057395399739
primary_activity_status 0.0034154240366053
```

Performance is environment-dependent and has no PASS threshold. R4 records
current timing/RSS/output-size separately from the historical reference.

## Geographic provenance note

`R4-BASELINE-GEO-001` inherits the R3 provenance note. The historical narrative
lists Pankower Tor and Landweg as no-stat-target PLR, while the frozen operational
F1.2a audit has Pankower Tor unavailable and Landweg as an available zero
private-household target. R4 reproduces the operational frozen artifact without
silently rewriting the historical narrative.

## Pre-delivery verification

An isolated integration run using the frozen raw MiD inputs, the R2 split and the
frozen reference files completed with `PASS` and reproduced:

- 3/3 primary exact artifacts;
- 4/4 compact exact artifacts;
- 23/23 structural checks;
- exact M snapshot SHA-256;
- numeric preservation/stability witnesses within tolerance.

This integration execution is development evidence only, not the user's official R4 run.
