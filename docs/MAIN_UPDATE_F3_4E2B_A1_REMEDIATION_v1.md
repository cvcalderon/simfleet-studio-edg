# MAIN update — F3.4e-2b A1 remediation v1

First authorized Time Schedule real-CAL execution failed during source-row validation before candidate scoring.

Classification: `IMPLEMENTATION_CONTRACT_MISMATCH`.

Frozen CAL evidence explicitly contains retained `__MISSING_CONTEXT__` optional upstream context; observed CAL target rows are not required to satisfy generated sequential prefix guardrails. Remediation preserves all 1243 isolated target rows and does not invent missing K.

After remediation: commit first, issue a new commit-bound A2 authorization, then rerun into a new RunBundle path. A1 authorization must not be reused.
