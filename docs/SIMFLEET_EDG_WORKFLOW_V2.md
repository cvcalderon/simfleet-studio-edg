# SimFleet-EDG — WORKFLOW V2

**Workflow ID:** `SIMFLEET_EDG_WORKFLOW_V2`  
**Status:** `MAIN_ADOPTED / REPOSITORY_SYNC_PENDING`  
**Adoption date:** 2026-10-07  
**Scope:** SimFleet-EDG scientific design, implementation, execution, validation and gate closure.

---

## 1. Purpose

Workflow V2 preserves the scientific rigor achieved in F0–F4.1c while reducing operational fragmentation.

The historical traceability remains valid. Workflow V2 does not reopen closed phases or replace scientific contracts. It standardizes how all *future* work packages are designed, implemented, executed, analyzed and closed.

The core rule is:

```text
MAIN designs and decides.
WORKER implements and remediates.
PROXMOX executes heavy workloads.
ANALYSIS interprets complex RunBundles.
MAIN alone closes scientific phases/gates.
```

---

## 2. Source-of-truth hierarchy

When two artifacts appear to disagree, use this precedence:

1. **Closed/frozen scientific contract for the same lineage and scope.**
2. **Most recent explicit MAIN gate/closure decision.**
3. **Current `MASTER_PROJECT_STATE` for status/navigation.**
4. **Execution PREOPEN / Work Package contract.**
5. **RunBundle evidence.**
6. **Worker notes / terminal logs / diagnostics.**
7. **Older handoffs or superseded drafts.**

`MASTER_PROJECT_STATE` is an index and control-plane snapshot. It does not silently rewrite a frozen scientific contract.

A newer artifact may supersede an older one only when it explicitly names the affected scope/lineage and the supersession is authorized by MAIN.

---

## 3. Four operational roles

### 3.1 MAIN

The MAIN thread is the control tower.

MAIN owns:

- scientific architecture;
- phase decomposition;
- contract design;
- allowed/forbidden evidence;
- NoFutureInformation boundaries;
- metrics and guardrails;
- thresholds before holdout opening;
- DESIGN_FREEZE;
- authorization of implementation/execution;
- review of ClosurePackage;
- PASS / MODIFY / FAIL;
- gate closure;
- `MASTER_PROJECT_STATE`.

MAIN should not perform heavy production execution.

### 3.2 WORKER

One Worker thread is opened per **coherent work package**, not per patch.

WORKER owns:

- repository inspection;
- exact-scope implementation;
- unit/focused tests;
- static verification;
- technical remediation;
- lint/type/full regression;
- production runner construction;
- RunBundle creation.

A technical remediation stays inside the same Worker work package unless it changes the scientific contract.

WORKER never closes a scientific phase or gate.

### 3.3 PROXMOX / execution environment

Heavy work runs outside MAIN, normally on the user's controlled VM/server.

Examples:

- N >= 100,000 population/demand generation;
- large OSM/PBF processing;
- OSRM / routing matrices;
- multiple seeds or ablations;
- model fitting;
- large Parquet joins;
- SimFleet execution;
- large validation sweeps.

Production execution must be CLI/module driven, not dependent on mutable notebook cell state.

### 3.4 ANALYSIS

Open a separate Analysis thread only when the RunBundle requires substantial statistical/scientific interpretation.

Use ANALYSIS for:

- candidate comparisons;
- subgroup diagnostics;
- sensitivity/ablation interpretation;
- distributional validation;
- large metric matrices;
- root-cause analysis of scientifically meaningful failures.

Skip a separate Analysis thread for trivial deterministic gates.

---

## 4. Work-package lifecycle

The default V2 lifecycle is:

```text
DISCOVERY / READ ONLY
        ↓
DESIGN
        ↓
DESIGN_FREEZE
        ↓
IMPLEMENTATION_PREOPEN
        ↓
WORKER IMPLEMENTATION
        ↓
TECHNICAL VERIFICATION
        ↓
IMPLEMENTATION_FREEZE
        ↓
EXECUTION_FREEZE / AUTHORIZATION
        ↓
PROXMOX EXECUTION
        ↓
RUNBUNDLE
        ↓
ANALYSIS (when useful)
        ↓
CLOSURE_PACKAGE
        ↓
MAIN DECISION
        ↓
PASS / MODIFY / FAIL
        ↓
CLOSED or controlled next iteration
```

Three artifacts are mandatory conceptually:

```text
PREOPEN
RUNBUNDLE
CLOSURE
```

Intermediate patches/remediations may exist but do not become independent work packages unless the scientific scope changes.

---

## 5. Three distinct freezes

### DESIGN_FREEZE

Defines **what** is scientifically authorized.

Examples:

- model family;
- purpose semantics;
- feature set;
- evidence registry;
- candidate set;
- metrics;
- thresholds;
- forbidden information.

### IMPLEMENTATION_FREEZE

Defines **which code** implements the frozen design.

Minimum identity:

```text
git_commit
exact_scope
tests
ruff
mypy when applicable
full_regression
verifier
```

### EXECUTION_FREEZE

Defines **what exact experiment is run**.

Minimum identity:

```text
git_commit
input hashes
config hashes
seed schedule
environment
runner
data split / holdout state
```

A scientific run is therefore identified by:

```text
Run =
  DataHash
+ ConfigHash
+ GitCommit
+ Seed/Schedule
+ Environment
```

---

## 6. State vocabulary

Use only the following top-level states for future work packages:

- `NOT_STARTED`
- `DISCOVERY_COMPLETE`
- `DESIGN_DRAFT`
- `DESIGN_FROZEN`
- `IMPLEMENTATION_PREOPEN`
- `IMPLEMENTATION_IN_PROGRESS`
- `IMPLEMENTATION_FROZEN`
- `EXECUTION_AUTHORIZED`
- `RUN_COMPLETE`
- `ANALYSIS_COMPLETE`
- `BLOCKED_TECHNICAL`
- `BLOCKED_SCIENTIFIC`
- `MODIFY_REQUIRED`
- `CLOSED_PASS`
- `CLOSED_FAIL`
- `SUPERSEDED`

A gate may use:

- `NOT_OPEN`
- `OPEN`
- `PASS_CLOSED`
- `FAIL_CLOSED`
- `DO_NOT_REOPEN`

Do not write `CLOSED` merely because code/tests pass. Only MAIN can issue scientific `CLOSED_PASS` / gate closure.

---

## 7. Technical remediation vs scientific change

### Technical remediation

May stay inside the current Worker:

- import/lint error;
- path typo;
- serialization bug;
- parser bug that restores frozen semantics;
- verifier bug;
- deterministic formatting issue;
- performance engineering that preserves exact outputs/contracts.

Record it in `attempt_history`.

### Scientific change

Must return to MAIN before implementation:

- feature change;
- candidate change;
- target/universe change;
- threshold change;
- metric change;
- data split/holdout change;
- source/evidence change;
- fallback semantics change;
- new information available at runtime;
- scope expansion;
- new interpretation of a frozen variable.

Scientific change requires a versioned contract amendment.

---

## 8. Git policy

Before a Worker applies changes:

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git rev-parse origin/main
git log -1 --oneline
```

The PREOPEN must define expected branch/parent.

If mismatch:

```text
STOP
diagnose
do not apply overlay
```

Before authoritative execution:

```text
focused tests
ruff
mypy where applicable
full regression
verifier
git diff --check
exact-scope audit
commit
push from PyCharm only
post-push verifier
```

Project rule retained from the historical workflow:

```text
NO git push from terminal.
Push exclusively from PyCharm.
```

---

## 9. Data policy

### In Git

Keep:

- code;
- configs;
- contracts;
- manifests;
- small audit tables;
- hashes;
- schemas;
- verifiers;
- small fixtures;
- closure summaries.

### Outside Git / Proxmox

Keep:

- raw surveys;
- OSM PBF;
- large derived Parquet/GeoParquet;
- large populations;
- routing matrices;
- SimFleet traces;
- large model artifacts;
- large RunBundles.

Git must contain enough provenance to identify the exact external bytes.

---

## 10. Notebook policy

Notebooks are allowed for:

- exploration;
- visual inspection;
- teaching;
- ad-hoc diagnostics.

They are not the authoritative implementation.

Production logic belongs in:

```text
src/simfleet_edg/**
```

and official execution through:

```text
python -m simfleet_edg.<module> --config ...
```

A notebook may call production functions; production functions must not depend on notebook state.

---

## 11. RunBundle V2

Every authoritative execution should be self-describing.

Minimum:

```text
run_manifest.json
execution_contract.yaml
environment.json
validation.csv
metrics.csv              # when metrics exist
performance.csv
issues.csv
run.log
checksums.sha256
SUMMARY.md
```

Add work-package-specific artifacts as needed.

The RunBundle must answer:

1. What was run?
2. On which code?
3. On which exact data?
4. With which config/seeds?
5. What validations passed/failed?
6. What metrics were produced?
7. What problems occurred?
8. Can another environment reproduce the run?

Large raw/derived data may stay external if manifest + hash + location class are recorded.

---

## 12. ClosurePackage V2

The ClosurePackage returned to MAIN is deliberately compact.

Required fields:

```text
work_package_id
implementation_commit
execution_commit
input_hashes
config_hashes
seed/schedule
environment_id

technical_validation
key_metrics
guardrails
subgroup_issues
performance
attempt_history
open_bindings
known_limitations

worker_recommendation
analysis_recommendation
```

Only MAIN adds:

```text
main_decision
scientific_closure_state
next_authorized_task
```

---

## 13. Sealed CAL / TEST / holdout data

For ordinary open engineering evidence:

```text
DESIGN_FREEZE
→ implementation
→ commit
→ execute
```

For sealed evidence:

```text
DESIGN_FREEZE
→ implementation
→ IMPLEMENTATION_FREEZE
→ exact commit authorization
→ wrapper verifies authorization
→ sealed data opened once
→ RunBundle
→ MAIN closure
```

Use explicit authorization packages only when they protect a real scientific boundary.

Do not create authorization artifacts for ordinary deterministic engineering steps when they add no protection.

---

## 14. Holdout invariants

Once a holdout has been consumed and its gate closed:

```text
candidate tuning = FORBIDDEN
threshold tuning = FORBIDDEN
same-lineage scientific tuning = FORBIDDEN
```

A genuinely new scientific lineage requires an explicit MAIN decision and new protocol.

Consumed holdouts are never reopened because a later module is inconvenient.

---

## 15. Failure rules

### Technical failure

```text
Attempt N = FAIL_TECHNICAL
→ technical remediation
→ Attempt N+1
```

Stay in same Work Package.

### Scientific failure

```text
Run evidence invalidates frozen assumptions
→ BLOCKED_SCIENTIFIC / MODIFY_REQUIRED
→ MAIN
```

No silent patching.

### Insufficient external evidence

```text
Run reports evidence
→ MAIN
→ versioned registry/contract amendment if justified
→ rerun only affected work package
```

---

## 16. Thread creation policy

Default:

```text
1 MAIN
1 Worker per coherent work package
Proxmox execution
Analysis only when useful
```

Do not open a new thread for:

- lint fix;
- one failing unit test;
- import order;
- filename correction;
- retry with same frozen contract.

Open a new Worker only for a new coherent problem or when isolation materially improves auditability.

---

## 17. Naming convention

Recommended:

```text
SimFleet-EDG — MAIN — Design & Gates
SimFleet-EDG — F4.1c-B — Implementation & Execution
SimFleet-EDG — F4.1c-B — Results Analysis
```

Artifact IDs:

```text
<PHASE>_<SUBPHASE>_<ROLE>_<VERSION>
```

Attempts belong in metadata:

```text
attempt_01
attempt_02
```

rather than inventing a new scientific phase for each retry.

---

## 18. MASTER_PROJECT_STATE maintenance

After every MAIN closure, update:

```text
MASTER_PROJECT_STATE.md
MASTER_PROJECT_STATE.json
MASTER_TRACEABILITY.csv
```

At minimum record:

- architecture module state;
- phase/work-package state;
- gate state;
- design freeze state;
- repository synchronization state;
- authoritative commit;
- consumed/sealed evidence;
- open bindings;
- next authorized task.

The master state is the first document read when starting a new thread.

---

## 19. Adoption rule

Workflow V2 applies prospectively from F4.1c-B onward.

Historical F0–F4.1b artifacts remain valid and are not renamed/repackaged.

F4.1c-A1–A5 are the first control-plane artifacts normalized under the transition to V2.

Current transition:

```text
F4.1c-A  = design frozen in MAIN control plane
repo sync = pending
F4.1c-B  = implementation PREOPEN ready
```

The first authoritative repository commit produced under Workflow V2 should also add the master-state/control-plane documents, unless MAIN explicitly chooses a separate documentation-only commit.
