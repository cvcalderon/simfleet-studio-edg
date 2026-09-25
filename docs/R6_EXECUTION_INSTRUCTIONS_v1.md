# R6 execution instructions v1

## 1. Entry state

Start from the accepted repository after R5:

```text
repository: simfleet-studio-edg
branch: main
accepted R5 commit: 379a577a5fff2ff4ec6b888405a616f546785e39
```

A later commit is acceptable only if it is explicitly derived from that accepted state and does not change frozen R0–R5 semantics.

Before applying the overlay:

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git fetch origin
git rev-list --left-right --count HEAD...origin/main
```

Required entry condition:

```text
branch = main
worktree = clean
ahead = 0
behind = 0
```

## 2. Apply overlay

Extract `SimFleet_EDG_R6_DMatch_Overlay_v1.zip` from the parent directory of the repository so that the archive's `simfleet-studio-edg/` tree overlays the existing repository.

Review the diff before committing:

```bash
cd simfleet-studio-edg
git status --short
git diff -- configs/reproduction/r6_d_match.yaml \
  src/simfleet_edg/common/demand_match.py \
  src/simfleet_edg/repro/r6_d_match.py \
  tests/test_r6_d_match.py
```

R6 must not modify accepted R0–R5 source files.

## 3. Preparation quality gates

Run in the official R0 environment:

```bash
pytest -q tests/test_r6_d_match.py
pytest -q
ruff check \
  src/simfleet_edg/common/demand_match.py \
  src/simfleet_edg/repro/r6_d_match.py \
  tests/test_r6_d_match.py \
  scripts/verify_r6_prep.py
python scripts/verify_r6_prep.py
```

All commands must pass before official execution is authorized.

`verify_r6_prep.py` also validates byte hashes of accepted R2/R4/R5 inputs and the frozen F0.3 reference tables.

## 4. Commit preparation overlay

Only after all preparation gates pass:

```bash
git add configs/reproduction/r6_d_match.yaml \
  src/simfleet_edg/common/demand_match.py \
  src/simfleet_edg/repro/r6_d_match.py \
  tests/test_r6_d_match.py \
  scripts/verify_r6_prep.py \
  notebooks/06_d_match_reproduction.ipynb \
  docs/R6_IMPLEMENTATION_NOTE_v1.md \
  docs/R6_EXECUTION_INSTRUCTIONS_v1.md \
  docs/MAIN_UPDATE_R6_PREP_v1.md

git commit -m "repro: add R6 D_MATCH reproduction"
git push origin main
```

Confirm clean synchronized state again before the official run.

## 5. Official execution

Run only in Proxmox/Jupyter/terminal, not in MAIN:

```bash
python -m simfleet_edg.repro.r6_d_match \
  --config configs/reproduction/r6_d_match.yaml \
  --out artifacts/runs/R6_d_match_v1
```

The runner requires a clean `main` synchronized with `origin/main` at run start.

## 6. Expected closure anchors

The run must reproduce:

```text
matched person-days = 100000
zero-trip days      = 15574
mobile days         = 84426
trip intents        = 291508
self matches        = 0
global fallbacks    = 0
```

Tiers:

```text
T1 = 94322
T2 = 3929
T3 = 1535
T4 = 214
T5 = 0
T6 = 0
```

Combined F2.1 validation:

```text
20/20 PASS
```

Historical bridge witness:

```text
2711e5542302f4c1b3b28ee8dab8b19bc044f0c61a143645e165aa32f5d437b5
```

## 7. Failure rule

If any preparation or execution check fails:

1. stop R6;
2. preserve the failed RunBundle unchanged;
3. do not delete or overwrite it;
4. diagnose root cause in the R6 worker thread;
5. do not start R7;
6. do not weaken an anchor or semantic invariant to obtain PASS.

A code/config correction requires a new commit and a separately named retry output directory.

## 8. Successful handoff

After PASS, create an R6 closure package containing at minimum:

- closure report;
- MAIN update;
- validation summary;
- issue register;
- checksums.

Do not transfer the large D_MATCH CSVs to MAIN unless specifically needed. Their identities and bridge hash belong in the closure evidence.
