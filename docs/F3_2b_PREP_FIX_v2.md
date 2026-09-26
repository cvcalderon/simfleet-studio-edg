# SimFleet-EDG — F3.2b preparation fix v2

## Scope

Minimal preparation-only correction applied on top of
`SimFleet_EDG_F3_2b_Materializer_Overlay_v1.zip`.

It does **not** change the frozen F3.2a contract, source manifest, dataset
schemas, row-count anchors, materialization semantics, TRAIN/CAL partitioning,
or any scientific decision.

## Corrections

1. `src/simfleet_edg/repro/f3_2b_materialize_training_data.py`
   - removes the unused local assignment `manifest = ...` while preserving the
     exact `materialize_training_data(...)` call and all downstream manifest
     enrichment/checksum logic;
   - resolves Ruff `F841`.

2. `scripts/verify_f3_2b_prep.py`
   - normalizes every verification result through built-in `bool(...)` before
     JSON serialization;
   - this converts Pandas/NumPy boolean scalars (e.g. results of `.all()` /
     `.any()`) to Python booleans without changing truth values;
   - resolves the `json.dumps()` failure observed in the official VM preflight.

## Validation performed during preparation

- Python compile: PASS for both modified files.
- Focused F3.2b tests: 8/8 PASS in the available preparation repository when
  executed with its `src` tree on `PYTHONPATH`.
- JSON-boundary normalization checked explicitly with Pandas boolean reductions.
- Full historical regression and Ruff are authoritative in the official
  `py312-edg` VM because the preparation copy is not a complete Git/runtime
  replica of the official repository.

## Traceability

The original v1 overlay and its checksum file remain historical delivery
evidence. This v2 package supersedes only the two Python file bytes listed
above. Use `F3_2b_PREP_FIX_CHECKSUMS_v2.sha256` to verify the post-fix bytes.
