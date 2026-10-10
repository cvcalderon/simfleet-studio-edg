# SimFleet-EDG — MASTER PROJECT STATE (synchronized snapshot)

**As of:** 2026-10-10
**Workflow:** `SIMFLEET_EDG_WORKFLOW_V2`
**Authority:** MAIN — scientific decisions; Worker — authorized edits only
**Status:** `MAIN_ADOPTED / DOC_ONLY_REPOSITORY_SYNC_PENDING`
**Scientific baseline commit reported:** `4c6481bc8bab4aca724020e29cc3ebbd69929771`
**Most recent MAIN closure:** `F4_2B_B_MAIN_SCIENTIFIC_CLOSURE_V1`.

> This index supersedes the outdated navigation snapshot dated 2026-10-07 **only for present project status**. Original frozen scientific contracts, historical documents, RunBundles and earlier closes are not amended by this sync. The archive ZIP contains no `.git`; the real-clone gate remains mandatory.

## 1. Sources of authority and reconciliation

The precedence from `SIMFLEET_EDG_WORKFLOW_V2.md` is:

1. Frozen scientific contract within its specific scope/lineage.
2. Most recent explicit MAIN scientific closure/gate decision.
3. This master navigation snapshot.
4. PREOPEN and work-package contracts.
5. Scientific RunBundle evidence.
6. Worker reports/transcripts.
7. Superseded handoffs/drafts.

Consequently, F4.2b-B's MAIN closure controls its scientific status, regardless of historical values still appearing in older snapshots. This document does **not** supersede F4.2a's selection, F4.2b-A's exploratory closure, or sealed M1/M2 evidence.

## 2. Architecture and gate state

| Module | State |
|---|---|
| M0 | `CLOSED_ACCEPTED` |
| M1 | `CLOSED_ACCEPTED` |
| M2 | `CLOSED_ACCEPTED` |
| M3 | `IN_PROGRESS` — pre-G3, only partial exploratory ESCORT integration |
| M4--M7 | `NOT_STARTED` |

| Gate | State |
|---|---|
| G0 | `PASS_CLOSED` |
| G1 | `PASS_CLOSED_FROZEN` |
| G2 | `PASS_CLOSED_FROZEN` |
| G3 | `NOT_OPEN` |

**Seals:** `MiD TEST = CONSUMED / DO NOT READ`; `F1 CAL = CLOSED / DO NOT REOPEN`. No same-lineage tuning of M1/M2 or D_GEN selected model components.

## 3. Accepted and frozen upstream inputs

- Accepted M1 population: **100,000 persons**; **54,828 households**; **642,364 resource relationships**. Personen enrichment for 92,056 persons; 7,944 roster-only persons must have absent personal-resource observations interpreted as `UNKNOWN`, never automatically `NO`.
- Household-size category `6_PLUS` remains top-coded. The 12 `BEZIRK` residential contexts are not precise home coordinates; `BEZIRK` is not LOR `BZR`.
- M2/D_GEN selected components: `DG_PARTICIPATION::PART_A::PA1`; `DG_TRIP_COUNT::COUNT_REF::REFERENCE`; `DG_ACTIVITY_CHAIN::CHAIN_A::CHA2`; `TIME_B_TB2`; `DIST_REF_REFERENCE`.
- Frozen lossy taxonomy projection: `PRIVATE_ERRAND → OTHER` after D_GEN and before the spatial adapter; record provenance.
- Spatial source: Berlin OpenStreetMap frozen materialization (F4.1c-C); `HOME` is a household-shared residential anchor; `ESCORT` must not use arbitrary POI.

## 4. F4 progression and authoritative commits

| Phase | Status | Commit / evidence |
|---|---|---|
| F4.1a | `CLOSED_PASS` | `8ccbb4d54601a7fdf65fe6cb549e688d2ba1558e` |
| F4.1b | `CLOSED_PASS` | `7e28e80c32dc16c478ea6916b636bafa58e917f5` |
| F4.1c-A1--A5 | frozen design/accepted preconditions | linked to `0958a673f0527b5bc87c16cb041e620f085ead87` |
| F4.1c-B | `CLOSED_PASS` | `0958a673f0527b5bc87c16cb041e620f085ead87` |
| F4.1c-C | `CLOSED_PASS` | `eebccc7a43eb7c1ef2661da3f357c0e5b01e72ef` |
| F4.1d | `CLOSED_PASS` | final taxonomy-hotfix lineage `61f29671a1e2a562d000bd6a1be45366a6630568` |
| F4.2a | `CLOSED_PASS_PRE_G3_CORE_SELECTED` | `7ec2c7aa884191ec77cf1fe6783756b78471f9c3` |
| F4.2b-A | `CLOSED_PASS_EXPLORATORY_NO_SELECTION` | latest `1fdfd815fb5085cbc674b66baecd932a9bcabff9` |
| F4.2b-B | **`CLOSED_PASS_EXPLORATORY_NO_SELECTION`** | `4c6481bc8bab4aca724020e29cc3ebbd69929771`; MAIN closure `F4_2B_B_MAIN_SCIENTIFIC_CLOSURE_V1` |
| F4.2c | `NOT_OPEN` | no authorization |
| G3 | `NOT_OPEN` | no test access |

The above commits are **reported in the handoff/closure**; the real Git graph must be inspected in the Worker clone before any edit. The scientific baseline commit is not the future documentation-sync commit.

## 5. F4.2a core and F4.2b-A/B details

### F4.2a — frozen core selection

- `S_NEAR = DIAGNOSTIC_BASELINE`
- `S_DIST = CORE_SELECTED_V1_PRE_G3`
- `S_ATTR = NON_SELECTABLE_ABLATION`
- Mean extended-real distance-error was `+INF` for all three variants; `S_DIST` selection was based only on the preregistered internal criterion. It does **not** establish independently measured destination accuracy.
- Original F4.2a TAR SHA-256, Worker reported: `9d97b2294e24d97709bc8ba4f103f94b5b21d2c4d64d7ed72efe35d24f816247`.

### F4.2b-A — synthetic relational variants

- 11 separate scenarios: `B0_NO_LINK` + 10 hypothetical SrV 2018/2023 × household-link-share variants (0,25,50,75,100%).
- **No B2 variant is selected**. SrV percentages describe purpose frequencies; they do not identify actual person-person relations.
- F4.2b-A original TAR SHA-256, Worker reported: `7aa0c4756f2bfca3e58988c4053083f52d4b1166621ba29ae6629cf7edc6bb3b`.

### F4.2b-B — MAIN scientific closure 2026-10-10

- MAIN decision: **`CLOSED_PASS_EXPLORATORY_NO_SELECTION`**, official record `F4_2B_B_MAIN_SCIENTIFIC_CLOSURE_V1.md`, SHA-256 `fa05842214c2a12dbfd75b19d62deff8ed7006f1a00c13d2e242016f5cf416de`.
- Source original B TAR SHA-256 **Worker verified (not directly by MAIN)**: `50397987086bd08655a7b692912970bbed1c3fee5439e069cece5e6bab37d99a`.
- 100,000 original person-days, 325,613 trips; partition: 84,619 CORE days/240,751 CORE trips + 15,381 ESCORT days/84,862 ESCORT-day trips. There are 18,871 ESCORT events.
- The V1 audit error stemmed from comparing 15,381 ESCORT resolution days against a 100,000-day global ledger. V2 reconciles both universes separately. 158/158 audit gates PASS in compact evidence; MAIN repeated 11/11 auditor tests and compact hash/consistency checks.
- CORE is `REFERENCED_ONLY` and frozen. Partial synthetic ESCORT spatialization is accepted only when all events on a day have valid inherited locations and the whole day satisfies S_DIST chain constraints. Missing cases remain in the ledger as unresolved.
- This is **integrity/contract acceptance**, not observed relationship validation, treatment-effect inference, full M3 success or G3 acceptance.

## 6. Frozen / forbidden actions

- Never read MiD TEST or reopen F1 CAL, G0/G1/G2 for this lineage.
- Do not regenerate M1/M2; refit D_GEN; change `PRIVATE_ERRAND → OTHER` bridge; or silently modify source/metric/threshold.
- Do not edit F4.2a CORE, F4.2b-A synthetic variants, F4.2b-B code or scientific RunBundles.
- Do not rerun F4.2a/F4.2b-A/F4.2b-B to support administrative synchronization.
- Do not select/merge B2, infer observed person-person relations, or use a coverage maximum as behavioral truth.
- F4.2c and G3 remain **NOT_OPEN**.
- Worker's terminal must not perform `git commit` or `git push`.

## 7. Binding state and outstanding scientific questions

- `F4-BIND-007`: outside-of-Berlin remains audit-only.
- `F4-BIND-ESCORT-001`: observed relationship unresolved; synthetic scenario linkage is not empirical resolution of the relationship.
- The 11 B2 exploratory scenarios vary purpose draws with variant-specific seeds; pHH comparisons are descriptive, not isolated causal effects.
- Any later F4.2c work requires a separate MAIN design authorization; G3 requires an independent scientific gate.

## 8. Exact next authorized work package (administrative only)

**ID:** `MAIN_MASTER_STATE_SYNC_F4_2B_B_V1`
**Type:** `DOC_ONLY / IMPLEMENTATION_PREOPEN`
**Scientific baseline parent required:** `4c6481bc8bab4aca724020e29cc3ebbd69929771` on real `main`; `HEAD = origin/main`, clean worktree before overlay.
**Allowlist:**

```text
docs/MASTER_PROJECT_STATE.md
docs/MASTER_PROJECT_STATE.json
docs/MASTER_TRACEABILITY.csv
```

MAIN provides the exact replacements in a versioned control-plane ZIP. Worker may only apply that overlay, validate Markdown/JSON/CSV consistency, run required non-mutating quality checks as applicable, inspect exact diff and stop at **PRE-COMMIT**. User performs commit and push in PyCharm only. Worker then verifies post-push HEAD and exact file hashes and returns compact logs. This administrative scope **does not** open a scientific work package, trigger simulation, or make any later phase automatically authorized.

## 9. Historical archive and provenance

The historical archive `F0-F4_1c.zip` and its original evidence are immutable. The 2026-10-07 master snapshot with F4.1c-C in PREOPEN is superseded *as a navigation index*, not rewritten as a scientific decision. The 2026-10-10 repository ZIP source snapshot has SHA-256 `8233bd33887b43a84a908057b0e489e50083d0e998c7a8befb1589297b8088d8` and contains **no Git metadata**; exact real clone commit is a Worker gate, not confirmed by archive filename.
