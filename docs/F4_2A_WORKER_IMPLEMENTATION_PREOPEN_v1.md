# F4.2a — Implementation PREOPEN (WORKER)

**Authority:** MAIN / Workflow V2. This overlay consists of **26 new paths only** on the frozen `61f29671a1e2a562d000bd6a1be45366a6630568` parent. `F4_2A_CORE_SPATIAL_CANDIDATE_DESIGN_FREEZE_v1.md` and `F4_2A_MAIN_SCIENTIFIC_PREOPEN_SPEC_v1.yaml` are copied **byte-for-byte** from the authority package; neither scientific specifications nor M1/M2/C code were edited. `G3`, `CAL`, `MiD TEST`, `F4.2b` and `F4.2c` are closed.

## Exact index and policies

For each purpose, construct a separate binary bounding-box tree over **all eligible** C locations, using projected EPSG:25833 X/Y. Internal nodes carry minimum/maximum X/Y and maximum S_ATTR weight. At each query, compute exact lower/upper possible Euclidean distances for the bounding box. For `S_NEAR`, the upper bound on score is `-d_min`. For `S_DIST`, the upper compatibility bound is `1` if the prior `p` lies within `[d_min, d_max]`, otherwise `d_max / p` when entirely nearer, and `p / d_min` when entirely farther. For `S_ATTR`, multiply this upper bound by maximum node weight. **Prune only when bound is strictly smaller than current best primary score**; examine all equal-scoring boxes for deterministic secondary ties. The algorithm does not form a dense trips × 88,879 matrix; candidate visits are counted. Exhaustive full-candidate oracle tests cover extreme priors, exact distance zero, symmetric ties and all policies.

`S_NEAR`: minimum Euclidean distance, then `location_id`. `S_DIST`: maximum compatibility, then `d <= p`, then minimum absolute separation error, then `location_id`. `S_ATTR`: maximum weighted compatibility, then higher raw compatibility, then identical `S_DIST` tie order. Polygon areas obtain purpose-specific midranks (equal areas share a rank) `q=(rank-0.5)/n` and weights `0.5+q`; missing areas and points are exactly neutral `1.0`. No capacity estimates or canonical attractiveness overwrite. Exact numeric comparison is used; **no epsilon**.

## M2→C spatialization

The algorithm resolves *destination activities* (not independent origin/destination per trip), carrying chosen destinations forward as the origin of the next trip. HOME is always the frozen C household anchor, including return home and zero-trip NoTrip days. WORK/EDUCATION are stable by person-purpose using the median HOME-origin incoming prior (fallback: all incoming priors), selected once from HOME and reused. BUSINESS/SHOPPING/LEISURE/OTHER are assigned per occurrence using their incoming M2 prior and resolved current origin. All origin/destination purpose fields, trip indices, time schedules and prior distances remain unmodified. All person-days containing ESCORT are excluded entirely, with explicit denominator and reason evidence. Initial non-HOME, malformed, unsupported, missing C anchors and NFI are blockers, never repaired silently.

`distance_prior_km` is compatibility scale, not an observed OD distance. The projected straight-line `d=0` compatibility is `0`, diagnostic absolute log ratio is literal `INF`, and zero/infinite counts are retained. `S_DIST` cannot be selected automatically as an independent scientific conclusion; the three preregistered mean/median/p90 inequalities are internal construct checks and MAIN decides closure.

## Gate sequence and operator handoff

1. The operator independently proves `main`, `HEAD==origin/main==61f2967`, clean Git, frozen source/protected hashes and upstream overlays.
2. Parent Ruff/mypy raw+normalized baselines must be captured before any edit, and must be bytewise identical to the frozen baseline; this gate was completed separately.
3. Install exactly the 26 new paths, execute the nine focused test modules, scoped Ruff+mypy, repository Ruff/mypy differential, full regression and static preopen verifier. Any new error, hash/scope discrepancy or unavailable tool -> **STOP/BLOCKER**.
4. Stop at **PRE-COMMIT**. The user alone may commit/push with PyCharm. No WORKER git commit/push.
5. After explicit push confirmation, validate one commit with 26 additions, original parent, clean repository and all exact off-repo inputs. Run full 100k model-support audit and two full M2 D_GEN replays. Only when all generated-demand and initial-HOME/ESCORT/NoTrip gates pass, run all three policies twice on the **same full frozen demand**. Hash-compare canonical spatial CSV bytes and all deterministic diagnostics. Record noncanonical walltime measurements in the RunBundle manifest separately from deterministic spatial output bytes. Return RunBundle to MAIN; do not self-close science.

### Execution limits

No frozen 100k M1 or frozen C full CSV.gz inputs were provided to the chat worker; therefore the user must execute official full replay on the real machine **after manual push**, not inside this PRE-COMMIT preparation. Do not substitute smoke data. Only existing project dependencies (`pyproj`, `pandas`, `numpy`, `scipy`) are permitted; no `pyproject.toml` changes.
