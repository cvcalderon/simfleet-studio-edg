# F3.4c-2b-R1 — Trip Count count-observability remediation

## Trigger

The first controlled F3.4c-2b attempt opened the three authorized CAL files and
failed before any candidate was evaluated:

`Positive Trip Count rows must exactly match CAL TripDay rows`.

The preserved `.partial` bundle contains only `failure.json` and its checksum.
No CRPS, bootstrap interval, grid selection, promotion decision, or candidate
guardrail file was produced.

## Observed structure

The authorized diagnostic established:

- Participation rows: 460.
- `TripDay=0`: 61.
- `TripDay=1`: 399.
- Trip Count target rows: 381.
- All 381 Trip Count rows are a subset of the 399 TripDay rows.
- Trip Count rows outside TripDay: 0.
- Trip Count target nulls: 0.
- Trip Count target range: 1..10.
- Count-target-unobserved TripDay rows: 18.

Set fingerprints:

- mobile context IDs:
  `b811d131a66555c0454a80ddbf557e4931c004eb76d93193f58c4acfb358044c`
- Trip Count context IDs:
  `e678c238964dfa6001132d0e5067b07629996529671c71f1573776027c2941f3`
- mobile person pairs:
  `6193a846389a459496684b944437077231b0be7e2c2432bb3d05c63e4ee5f4c2`
- Trip Count person pairs:
  `446075a7479ad710ed49be6c9e24cf9f465d71c7882251ef216d51d1d5ef6ffb`

## Interpretation

`TripDay` and observable Trip Count are separate targets. A positive mobility day
does not imply that its K target is available. The 18 missing K targets are labeled
`COUNT_TARGET_UNOBSERVED`. This remediation deliberately does not infer a raw-data
reason that is not encoded in the frozen CAL target table.

## Correct evaluation universes

The primary ISOLATED CRPS remains unchanged: 381 rows with observed positive K.

Count-based generated-outcome guardrails require an observed K. Their evaluable
person-day universe is therefore:

`61 observed NoTrip with known K=0 + 381 TripDay with observed K = 442`.

The 18 positive TripDay rows without observable K are excluded from Trip Count
guardrails. They are not zero, not imputed, and not used to redefine the primary
metric.

Participation validation remains on its already-frozen 460-row surface.

## Anti-post-selection property

This correction is frozen before any Trip Count candidate metric was computed.
The failed attempt stopped during input-universe validation, before candidate
adapter evaluation. Therefore no candidate CRPS or guardrail result was available
when this remediation was defined.

## Unchanged protocol

No candidate, margin, guardrail tolerance, seed, bootstrap count, CRN rule,
ISOLATED/PROPAGATED ordering, upstream PA1 selection, TEST boundary, or G2 state
is changed.
