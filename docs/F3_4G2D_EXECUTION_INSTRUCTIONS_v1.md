# F3.4g-2d — Execution instructions v1

Required parent:

`beeb79a79e81aaaff3041542c3a9f3c08937e1dc`

Required preserved RunBundle:

`$HOME/Downloads/F3_4g2c_A1_joint_real_cal_run_v1`

This phase must not reopen CAL source files.

Validation sequence:

1. require exact clean synchronized parent;
2. apply overlay;
3. Ruff;
4. focused tests;
5. full regression;
6. verify preserved A1 RunBundle checksums/provenance/metrics;
7. confirm all 14 decision metrics pass;
8. confirm TEST eligibility true but TEST open authorization false;
9. `git diff --check`;
10. exact overlay scope;
11. STOP before staging/commit.
