# MAIN update — C-IMPL-02 / R0 preparation

## Change class

Engineering implementation only. No scientific baseline change.

## Decision implemented

Part C is `Python-library-first`:

- core logic in importable Python modules;
- Jupyter as inspection/analysis surface;
- official executions via module/CLI;
- Proxmox/VM as execution environment.

## Current status

- C-IMPL-01: SUPERADO (validated on VM; base commit `f123d7d`)
- C-IMPL-02: implementation package prepared; VM validation pending
- R0: implementation prepared; official execution pending
- R1–R7: pending

## R0 outputs expected

`environment.json`, `python_packages.csv`, `pip_freeze.txt`, `r0_validation.csv`, `performance.csv`, `manifest.json`, `run.log`, `checksums.sha256`, and a frozen config snapshot.

R0 must be executed only after the C-IMPL-02 code is committed/pushed and the worktree is clean and synchronized with upstream.
