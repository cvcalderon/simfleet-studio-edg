# F1-P_CONSTR-IMPL-01 A1 MAIN Freeze — validation instructions v1

Required parent:

`2b08eeb1440c1fd8171917b91047b1b0c6be46f6`

Required preserved evidence:

- `$HOME/Downloads/F1_PCONSTR_IMPL01_A1_official_run_v1/`
- `$HOME/Downloads/F1_PCONSTR_IMPL01_A1_official_run_v1.zip`
- RunBundle ZIP SHA256 `de4e70a07483f594053c2bb6b04e82e8be8d38191e0336bebad3e38186175de0`

Validation sequence:

1. exact clean synchronized parent;
2. verify preserved RunBundle ZIP hash and integrity;
3. apply freeze overlay;
4. Ruff on freeze verifier and focused tests;
5. focused tests;
6. full regression;
7. independently verify preserved RunBundle and rederive Stage1/2/3 from CSV evidence;
8. verify 3,532,081 person-domain total and exact Bezirk totals;
9. verify 38 published-zero cells remain zero;
10. verify aggregate household-size divisibility for sizes 1–5;
11. verify CAL/TEST/1000A-1035/F3 boundaries;
12. `git diff --check`;
13. exact overlay scope;
14. STOP before staging/commit.
