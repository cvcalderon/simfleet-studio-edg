# F3.1a lint fix v2

## Scope

Mechanical Ruff-only correction after the official VM pre-flight of the F3.1a contract overlay.

Reported findings:

- `I001` in `scripts/verify_f3_1a_contract.py`;
- `I001` in `tests/test_f3_1a_contract.py`.

## Changes

Only import ordering/spacing was changed:

- standard-library imports grouped and sorted;
- third-party `yaml` import separated from standard library.

No contract YAML, feature registry, component mapping, invariant, decision, target universe, runtime boundary, or scientific semantics were modified.

## Local validation

- `python -m py_compile scripts/verify_f3_1a_contract.py tests/test_f3_1a_contract.py` — PASS
- `pytest -q tests/test_f3_1a_contract.py` — 8/8 PASS
- `python scripts/verify_f3_1a_contract.py` — PASS

Ruff must be rerun in the official VM.
