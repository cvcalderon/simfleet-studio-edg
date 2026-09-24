# C-IMPL-02 + R0 preparation — implementation note v1

## Status

Prepared for application to the validated `simfleet-studio-edg` repository.

This delta does **not** execute R0. It adds the reusable environment-capture core, R0 orchestration, configuration, tests and notebook inspection surface.

## Architecture

- distribution/repository: `simfleet-studio-edg`
- import package: `simfleet_edg`
- Python: 3.12
- Jupyter: inspection and scientific interaction only
- authoritative logic: `src/simfleet_edg/`
- official R0 execution: Python module/CLI, not notebook state

## Added

- `configs/reproduction/r0_environment.yaml`
- `src/simfleet_edg/common/environment.py`
- `src/simfleet_edg/repro/r0_environment.py`
- `tests/test_r0_environment.py`
- `scripts/verify_c_impl_02.py`
- `notebooks/00_environment_check.ipynb`

## Modified

- `src/simfleet_edg/__main__.py`: user-facing CLI name is now `simfleet-studio-edg`.

## Official sequencing

1. install `.[dev,reproduction,notebooks]`;
2. register the Jupyter kernel;
3. run tests, Ruff and C-IMPL-02 verifier;
4. commit and push C-IMPL-02;
5. verify clean/synchronized `main`;
6. execute official R0 into a new ignored `artifacts/runs/...` directory;
7. return compact R0 outputs for closure.

No F0–F2 scientific decision is changed by this implementation.
