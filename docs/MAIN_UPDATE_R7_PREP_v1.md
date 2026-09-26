# MAIN update — R7 preparation v1

- R6 is closed as `SUPERADO`; accepted run is `R6_d_match_v1_retry01`.
- R7 reproduces historical F2.2 diagnostics only; it does not redesign metrics.
- Reference scope remains strict TRAIN and TEST remains sealed.
- R7 freezes/reproduces metric definitions, not G2 acceptance thresholds.
- Historical F2.2 witness set contains 11 artifacts.
- Local candidate reproduction: 10/11 byte-exact; `global_metrics` numerically
  equivalent with maximum absolute difference about `1.19e-13` under `atol=1e-12`.
- Official execution must occur only after overlay quality gates, commit and push.
- R8/F3 work remains blocked until R7 closure.
