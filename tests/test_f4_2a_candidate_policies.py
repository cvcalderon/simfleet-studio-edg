from __future__ import annotations

import math

import pytest

from simfleet_edg.spatial.candidate_policies import (
    Choice,
    abs_log_ratio,
    attractive_midrank_weights,
    better,
    compatibility,
    extended_metrics,
    preregistered_promotion,
)


def test_zero_distance_extended_real() -> None:
    assert compatibility(0, 2) == 0
    assert abs_log_ratio(0, 2) == math.inf
    assert compatibility(2, 2) == 1
    with pytest.raises(ValueError):
        compatibility(-1, 1)


def test_dist_ties_prefer_below_prior_then_difference_then_id() -> None:
    below = Choice("z", 0.5, compatibility(0.5, 1))
    above = Choice("a", 2.0, compatibility(2, 1))
    assert better(below, above, "S_DIST", 1)
    assert not better(above, below, "S_DIST", 1)
    assert better(Choice("a", 0.5, 0.5), below, "S_DIST", 1)


def test_attractive_midrank_area_polygon_point_missing() -> None:
    weights = attractive_midrank_weights({"a": 10, "b": 20, "z": 20,
                                          "point": None, "missing": float("nan")})
    assert weights["a"] == 0.5 + 0.5 / 3
    assert weights["b"] == 0.5 + 2.0 / 3
    assert weights["z"] == 0.5 + 2.0 / 3
    assert weights["point"] == 1.0 == weights["missing"]


def test_extended_metric_infinity_is_not_dropped() -> None:
    metrics = extended_metrics([1.0, 2.0, math.inf, math.inf])
    assert metrics["count"] == 4
    assert metrics["inf_count"] == 2
    assert metrics["median"] == "INF"
    assert metrics["mean"] == "INF"
    assert metrics["p90"] == "INF"
    assert preregistered_promotion(metrics, metrics)
    assert not preregistered_promotion({"median": 0., "mean": 0., "p90": 0.}, metrics)
    with pytest.raises(ValueError):
        extended_metrics([])
