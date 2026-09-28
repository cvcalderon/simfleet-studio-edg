# F3.4c-2b-A2 — RunBundle verifier empty-decision remediation

## Trigger

The controlled A2 Trip Count CAL run completed with `status=PASS` and wrote a
checksum-valid RunBundle. The RunBundle verifier then failed while parsing
`promotion_decisions.csv` because the file is empty.

## Why an empty decision table is valid here

All four non-reference Trip Count artifacts failed the frozen ISOLATED guardrails.
Therefore no family had an eligible within-family winner.

The selection algorithm correctly left the incumbent as:

`DG_TRIP_COUNT::COUNT_REF::REFERENCE`.

Because no challenger was eligible for promotion:

- promotion decision rows = 0;
- bootstrap comparison rows = 0.

This is not missing evidence. It is the explicit consequence of the frozen
lexicographic protocol: guardrails are required before a challenger enters a
promotion comparison.

## Remediation

The verifier now:

1. accepts a syntactically empty promotion/bootstrap CSV as an empty typed table;
2. derives the expected number of promotion decisions from
   `selected_within_family` in `grid_selection.csv`;
3. requires promotion rows to equal that eligible-family-winner count;
4. requires bootstrap rows to equal promotion rows;
5. keeps every CAL cardinality, checksum, TEST, upstream, and G2 check unchanged.

The existing A2 RunBundle is not modified and CAL must not be rerun.
