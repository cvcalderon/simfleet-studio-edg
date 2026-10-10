# SimFleet-EDG — F4.2b-B · Partial-domain ESCORT spatial integration

**MAIN scientific design freeze v1 — 2026-10-10**  
**Status:** `DESIGN_FROZEN_V1 / IMPLEMENTATION_NOT_AUTHORIZED / NO_G3`  
**Authority:** MAIN. This design extends F4.2b-A without reopening its synthetic relation generation or selecting any B2 policy.

## 1. Decision and epistemic boundaries

MAIN adopts a **per-variant, append-only partial-domain integration**. All eleven F4.2b-A proposals (B0 + ten B2 sensitivity hypotheses) stay separate. Neither HH000 nor HH050 is chosen as observed or scientifically optimal. A variant is an illustrative synthetic *scenario*; a successful location inheritance does not establish real person-person linkage, joint trips, temporal co-travel, or validation of human behaviour.

This is not a replacement for the frozen F4.2a `S_DIST` CORE, and not full M3 or G3. The integration never changes one CORE byte. The frozen M2 person-day/trip ledger remains fully represented even when a day has no usable spatial realization.

## 2. Source identities (verified original archives)

- F4.2a official RunBundle SHA-256: `9d97b2294e24d97709bc8ba4f103f94b5b21d2c4d64d7ed72efe35d24f816247` — 100,000 person-days; 325,613 trips; CORE 84,619 days/240,751 trips; ESCORT excluded 15,381 days/84,862 trips.
- F4.2b-A official RunBundle SHA-256: `7aa0c4756f2bfca3e58988c4053083f52d4b1166621ba29ae6629cf7edc6bb3b` — 18,871 ESCORT proposals per variant, 11 variants, exact A/B outputs and separate 7,621-anchor sidecar; generated at Worker-reported HEAD `1fdfd815fb5085cbc674b66baecd932a9bcabff9`.
- The source TARs cannot independently establish the remote Git state; Worker real-clone entry must attest `HEAD=origin/main` and clean worktree at the accepted commit before editing.
- Historical F4.2b-A hypothetical proportions are not measurements of Berlin household linkage. SrV 2018/2023 published purpose proportions are descriptively transferred as scenario inputs only. Unknown HOME transport share remains `NOT_IDENTIFIED`, **not** empirically zero.

## 3. Independent MAIN day-link eligibility audit

For each B2 variant, group the 18,871 original proposals by frozen `row_id`, assert exactly 15,381 ESCORT days, and mark link-complete only if *every* ESCORT event on that day has `status=RESOLVED_LOCATION_ONLY`, a nonself M1 person and frozen anchored `target_location_id`. These counts have been recomputed directly from original gzip bytes; see `F4_2B_B_MAIN_VERIFIED_LINK_COMPLETE_UPPER_BOUNDS_v1.csv`.

Even a link-complete day is **not yet spatialized**: it must pass the second (independent) spatial-feasibility gate below. The largest link-complete count across the ten illustrative variants is 11,665 days / 62,751 associated trips (`B2_SRV2023_HH000`), and the smallest among the ten is 2,443 days / 12,574 trips (`B2_SRV2018_HH100`). These are upper bounds, not observed linkage rates nor achieved spatial coverage.

The frozen M2 ESCORT-day chains have been screened for trip-index continuity, initial HOME origin and origin activity matching the immediately preceding destination activity: **84,862 trips, 0 inconsistencies found**. This proves structural syntax of these inputs; it does not prove spatial feasibility.

## 4. Deterministic node-binding and trip reconstruction contract

Process complete ESCORT days in ascending original `(row_id, trip_index)` order. Use only the selected **CORE S_DIST** rules, unchanged, for all non-ESCORT nodes.

1. The initial node of each day is the accepted household HOME ResidentialAnchor, not a new POI. Verify the first trip's origin is HOME.
2. The destination of a trip is its activity node indexed by `row_id + trip_index`. For destination `ESCORT`, lookup **exactly the event-specific** proposal `event_id = row_id:trip_index`. Require `RESOLVED_LOCATION_ONLY`; inherit its target's `target_location_id` directly, and independently validate that it matches the person's CORE or sidecar stable anchor for the declared target purpose and M1 identity. Do not choose another place for ESCORT.
3. For destination HOME, use the person's frozen M1 household home. For WORK/EDUCATION, reuse the person's exact frozen `S_DIST` stable anchor (CORE or append-only sidecar, as applicable; WORK is represented as `WORK_COMMUTE` in the stable-anchor registry). For BUSINESS/SHOPPING/LEISURE/OTHER, apply the original `S_DIST` eligible supply, compatibility score and frozen tie-breaks for **that occurrence**, using current resolved origin. NO new stochastic selection or attractiveness heuristic.
4. Trip `i` origin location is **identically trip `i-1` destination location**, not a new lookup. This covers ESCORT→other, ESCORT→ESCORT and other→ESCORT links. Preserve original `origin_activity`, `destination_activity`, trip index, times, durations and strictly positive M2 `distance_prior_km`; an ESCORT node inherited as a destination is also the next origin. Never synthesize route, mode or co-travel.
5. Compute geometrical EPSG:25833 straight-line distances for descriptive diagnostics; `d=0` is allowed, and `abs_log_ratio=+INF` as the frozen V1 interpretation, **without epsilon**. No retrospective alteration of F4.2a selection criteria. Distance mismatch is a diagnostic, not permission to replace a linked target.
6. If *any* event, target reference, node, spatial supply lookup, day continuity or frozen invariant fails, keep the **whole day** typed unresolved and **all its original trips** in the accounting ledger without invented location IDs. No partial day is labelled spatialized. F4.2a CORE records must stay byte-for-byte unchanged.

Pre-flight audit must verify that the existing 7,621 sidecar keys plus 30,055 CORE keys cover the required stable person-purpose keys in every attempted day. **Do not silently compute further sidecar anchors**; if extra keys are needed, STOP and return a new explicit scope request. This check is not assumed PASS just because the 7,621 existing sidecar keys were valid.

## 5. Day and trip accounting / state machine

Each variant maintains a **100,000-row day ledger** and a **325,613-row trip ledger**, referencing original IDs and inputs, without duplicating F4.2a CORE output data. Core days are `CORE_FROZEN_SPATIALIZED`. ESCORT days are one of:

- `ESCORT_LINK_INCOMPLETE` — one or more B2 event failures / B0 no-link; store all event reason codes, do not spatialize this day.
- `ESCORT_LINK_COMPLETE_SPATIAL_PENDING` — transient state before second gate; never count as completed output.
- `ESCORT_SPATIALIZED_SYNTHETIC_LOCATION_ONLY` — every trip bound; **not** proof of observed escort, temporal co-travel or mode matching.
- `ESCORT_SPATIAL_UNRESOLVED` — every relation location was proposed but at least one required spatial invariant or anchor failed; no partial-day promotion.
- `ESCORT_FATAL_INPUT_GATE` — upstream or data-contract inconsistency that should stop the run, not simply be counted as normal unresolved uncertainty.

Release files contain **no PENDING**. For all 11 variants, ledger partitions must sum to 84,619 CORE + 15,381 ESCORT = 100,000 and 240,751 CORE trips + 84,862 original ESCORT-day trips = 325,613. All 11 event files keep 18,871 events exactly; zero silent filtering. A full spatialized trip must have nonempty source/destination `LocationRef` in frozen Berlin closed-world supply or accepted HOME anchors; an unresolved trip carries blank spatial location fields, explicit parent-day cause, and original M2 intent fields. Never merge rows from different variant IDs.

One per-variant compact **append-only spatial delta** is sufficient; store CORE by immutable `RunBundle + SHA` reference, never copy it and inadvertently change compression/row order. The complete **logical integration view** = frozen F4.2a CORE S_DIST plus accepted ESCORT day/trip deltas, all labelled by variant. No canonical unified single-policy full-M3 view is produced until a later MAIN authority decision.

## 6. Predeclared diagnostics (non-selective)

Report per variant: link-complete days, spatial-feasible days, spatialization failures by typed cause, counted integrated trips, unresolved days/trips, resolved ESCORT events, inherited target types and intra/extrahousehold scope, rate versus **all 15,381 ESCORT days** and **all 84,862 excluded trips**, plus total 100,000/325,613 coverage when paired with CORE. Keep B0 explicitly nonlinking and all ten B2 as uncertainty/scenario envelopes.

For newly spatialized days, report p50/p90 extended-real log distance mismatch and d=0 rates, strict original M2 priors and deterministic candidate-visit counts as technical characterization only. The metric is internally related to the chosen M2 prior; no independent observed destination accuracy, causality, or linkage calibration is implied. Do not identify which pHH is 'true' from the highest coverage or the lowest error.

**Confounding:** B2 source-purpose draws change with variant ID. No comparison of pHH levels is an isolated causal treatment effect. A common-random-number paired study would need a *new*, separately preregistered experiment and is out of F4.2b-B scope.

## 7. Hard gate / no-go for F4.2c and G3

Even if every *link-complete* day spatializes, each of the ten B2 variants has unresolved ESCORT days (minimum 3,716 for HH000 2023). This design therefore closes neither full F4.2b nor M3. G3/TEST are not available here. A later F4.2c partial-domain scientific claim, if desired, requires a new explicit MAIN decision with its domain, denominators and limits; it must not be implicitly inferred from a successful experimental RunBundle.

Other frozen protections: M1 households/persons/resources; selected five M2/D_GEN artifacts; F4.1c-C sources/supply; F4.1d taxonomy; complete F4.2a RunBundle; all B2 relation proposals and source priors; 30,055 CORE and 7,621 sidecar stable anchors. No CAL access, no MiD TEST reads, no new source requests, no D_GEN or F4.2a reruns, no promotion of HH variants.

## 8. Gate to implementation

This package approves **design only**. Implementation and scientific execution are NOT authorised. Before any Worker code edits, MAIN must audit an up-to-date Git archive at Worker-reported `1fdfd815fb5085cbc674b66baecd932a9bcabff9`, freeze an exact new-path allowlist and regression/baseline fingerprints, locate the official F4.2a S_DIST callable and acceptable invocation/arguments and verify immutable M1/C supply inputs are available. If those requirements imply changes to already frozen code, issue a new scoped blocker instead of silently patching.

Expected implementation procedure after a **separate** authorization: real-clone gate → baseline Ruff/mypy fingerprints → implementation → focused tests → differential quality → full regression → canonical verifiers → exact-scope audit → **PRE-COMMIT STOP** → user manual PyCharm commit + push → post-push A/B determinism → RunBundle → MAIN scientific audit. No G3 access.
