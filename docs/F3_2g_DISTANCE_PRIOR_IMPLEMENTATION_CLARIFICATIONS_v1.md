# F3.2g — DG_DISTANCE_PRIOR pre-CAL implementation clarifications v1

These clarifications resolve implementation details that the F3.1 semantic/model freeze did not specify fully. They are frozen **before CAL is opened** and do not add a new candidate family.

## 1. DIST_FEATURES_V1 concrete encoder

F3.1c freezes the semantic set as static core + weekday + season + generated K + generated chain + generated times. F3.2a exposes the corresponding source analogues. F3.2g maps them as follows:

Categorical:
- `age_infr_class`
- `sex`
- `primary_activity_status`
- `household_size_class`
- `source_weekday`
- `source_season`
- `origin_activity_analogue`
- `destination_activity_analogue`
- `departure_period_analogue`

Numeric:
- `source_trip_count_analogue`
- `departure_clock_minute_analogue`
- `arrival_clock_minute_analogue`
- `duration_from_clock_min_analogue`

`generated_activity_chain` is represented for the current trip by origin/destination activity analogues. `generated_trip_times` is represented by departure clock/period, arrival clock and planned duration analogues.

Encoding: deterministic full one-hot for categorical TRAIN vocabulary + raw numeric values. Numeric missingness remains native NaN for LightGBM. There is no rare-category pooling. Missing/unseen categorical tokens are explicit.

The 80 rows with missing K, 32 with missing valid time context and 217 with unresolved transition context stay in the 5,617-row target universe. Quality/status fields themselves are not predictors.

## 2. Weighted inverse-ECDF knot convention

F3.1c says `weighted linear inverse-ECDF` but does not define the exact interpolation knots. F3.2g freezes:

`LINEAR_WEIGHTED_CUMULATIVE_MASS_KNOTS_V1`

- aggregate equal distances;
- sort ascending distance;
- W_GEW defines probability mass;
- cumulative weighted mass defines the ECDF knots;
- prepend `(u=0, min_train_distance)`;
- interpolate linearly in cumulative probability.

The same convention is used by the unconditional reference and DIST_A cells.

## 3. DIST_B common LightGBM training parameters

The F3.1c DIST_B rows freeze quantiles, depth, leaves, min leaf and L2, but do not state learning rate or estimator count. F3.2g therefore freezes before CAL:

- learning rate: `0.05`
- estimators: `200`

No search over these values is authorized.

## 4. DIST_B full-u quantile reconstruction

The seven frozen quantiles do not by themselves define a draw for every `u in [0,1]`. F3.2g freezes:

`DIST_B_QUANTILE_RECONSTRUCTION_V1`

1. clamp predicted quantile knots to the global strict-TRAIN raw-wegkm min/max;
2. apply cumulative maximum in ascending quantile order;
3. prepend `(q=0, global TRAIN min)`;
4. append `(q=1, global TRAIN max)`;
5. sample by linear interpolation in quantile probability.

This is a runtime reconstruction convention, not CAL-derived calibration.
