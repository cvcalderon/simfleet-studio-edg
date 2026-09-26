# R7 execution instructions v1

## Entry condition

Start from the accepted R6 code baseline or a clean, synced descendant containing
R6 closure-compatible artifacts. The official R7 run must start from `main`, with
clean worktree and `ahead=0`, `behind=0` relative to `origin/main`.

## Quality gates before commit

```bash
pytest -q tests/test_r7_f2_2_diagnostics.py
pytest -q
ruff check \
  src/simfleet_edg/common/diagnostic_metrics.py \
  src/simfleet_edg/repro/r7_f2_2_diagnostics.py \
  tests/test_r7_f2_2_diagnostics.py \
  scripts/verify_r7_prep.py
python scripts/verify_r7_prep.py
```

Commit and push the R7 overlay before the official run.

## Official run

```bash
python -m simfleet_edg.repro.r7_f2_2_diagnostics \
  --config configs/reproduction/r7_f2_2_diagnostics.yaml \
  --out artifacts/runs/R7_f2_2_diagnostics_v1
```

Never overwrite a failed RunBundle. A retry must use a new directory such as
`R7_f2_2_diagnostics_v1_retry01`.

## Expected acceptance evidence

```text
F2.2 validation                 18/18 PASS
source hashes                   15/15 PASS
historical witnesses            11/11 accepted
```

Ten witnesses should be byte-exact. `global_metrics` is accepted only when it is
numerically equivalent within the frozen `1e-12` tolerance.

The run must also prove:

- strict-TRAIN reference only;
- no TEST outcomes consumed;
- no mode metric;
- no `km_routing` distance target;
- LOW_N cells flagged rather than pooled;
- G2 not evaluated;
- numeric G2 thresholds remain unfrozen.

After PASS, preserve and submit the complete RunBundle to MAIN for R7 closure.
