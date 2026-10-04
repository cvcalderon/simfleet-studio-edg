# F1-P_CONSTR-IMPL-02 — PRE-COMMIT execution

1. Apply the overlay only on clean synchronized `main` at commit `6ca6a2fd1f577433237fce3cca8763c84d8f68fe`.
2. Do not read CAL, MiD TEST or `1000A-1035`.
3. Run checksums, focused tests, full regression, Ruff, verifier, `git diff --check` and `git status --short`.
4. STOP before `git add` / commit / push.
5. Return the complete terminal output to MAIN.
