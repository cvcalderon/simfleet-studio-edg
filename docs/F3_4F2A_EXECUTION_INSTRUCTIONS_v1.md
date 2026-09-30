# F3.4f-2a execution instructions

Use only the package-level `apply_and_run.sh` from `~/Downloads` while the repository is exactly at parent commit `6ef56286460939e57b4a01703f56b47967615bea`, clean and synchronized with `origin/main`.

The script applies the overlay, runs Ruff, focused tests, the full regression, verifies the PREOPEN contract, generates a synthetic RunBundle under `~/Downloads`, verifies that RunBundle, checks the Git diff/scope, and stops before staging or commit.

Do not run any real CAL command in this phase.
