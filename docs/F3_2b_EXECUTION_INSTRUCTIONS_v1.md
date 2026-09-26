# F3.2b — execution instructions v1

## Entry

Required design parent:

```text
25345916d80c7d810bb7d4699bfa056ed28cc4e8
```

Apply the overlay while HEAD remains that commit. Run focused/full tests, Ruff and `scripts/verify_f3_2b_prep.py`. Do not materialize or commit if any preparation gate fails.

## Commit

After preparation PASS, commit the implementation and push `main`. The official materializer requires a clean, synchronized `main` whose history contains the F3.2a design parent.

Suggested commit:

```bash
git commit -m "feat: implement F3.2b D_GEN training data materializer"
git push origin main
```

## Official execution

Only after the implementation commit is clean/synchronized:

```bash
python -m simfleet_edg.repro.f3_2b_materialize_training_data \
  --config configs/f3/f3_2b_materialize_training_data.yaml \
  --out artifacts/model_data/F3_2a_training_data_v1
```

The destination must not already exist. A failed output is preserved; use an explicit retry suffix rather than overwriting it.

Expected frozen row counts:

```text
TRAIN       context 2200 | participation 2154 | count 1791 | chain days 1422
            transitions 4872 | time 6103 | distance raw 5617 | expanded 6145
CALIBRATION context 469  | participation 460  | count 381  | chain days 319
            transitions 1065 | time 1243 | distance raw 1147 | expanded 1257
```

Then verify:

```bash
cd artifacts/model_data/F3_2a_training_data_v1
sha256sum -c checksums.sha256
```

Do not inspect CAL model performance in F3.2b. This phase materializes evidence only.
