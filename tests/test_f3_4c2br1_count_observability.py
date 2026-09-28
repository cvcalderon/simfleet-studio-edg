from __future__ import annotations

import pandas as pd
import pytest

from simfleet_edg.evaluation.trip_count_cal_real import (
    _build_count_observability_universe,
)


def _cfg() -> dict:
    return {
        "cal_input": {
            "expected_participation_rows": 5,
            "expected_observed_tripday_rows": 4,
            "expected_known_notrip_rows": 1,
            "expected_isolated_rows": 3,
            "expected_count_target_unobserved_tripday_rows": 1,
            "expected_count_guardrail_person_days": 4,
        }
    }


def _participation() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "context_row_id": ["a", "b", "c", "d", "e"],
            "target_trip_day": [0, 1, 1, 1, 1],
        }
    )


def _positive() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "context_row_id": ["b", "c", "d"],
            "target_trip_count": [1, 3, 2],
        }
    )


def test_unobserved_positive_count_is_excluded_not_zero_imputed():
    evaluable, stats = _build_count_observability_universe(
        _participation(),
        _positive(),
        _cfg(),
    )
    assert list(evaluable["context_row_id"]) == ["a", "b", "c", "d"]
    assert list(evaluable["observed_trip_count_full"]) == [0, 1, 3, 2]
    assert "e" not in set(evaluable["context_row_id"])
    assert stats["count_target_unobserved_tripday_rows"] == 1
    assert stats["count_guardrail_person_days"] == 4


def test_trip_count_rows_must_be_subset_of_tripday_rows():
    positive = pd.DataFrame(
        {
            "context_row_id": ["a", "b", "c"],
            "target_trip_count": [1, 3, 2],
        }
    )
    with pytest.raises(ValueError, match="subset"):
        _build_count_observability_universe(
            _participation(),
            positive,
            _cfg(),
        )


def test_expected_unobserved_cardinality_is_enforced():
    cfg = _cfg()
    cfg["cal_input"]["expected_count_target_unobserved_tripday_rows"] = 0
    with pytest.raises(ValueError, match="count-target-unobserved"):
        _build_count_observability_universe(
            _participation(),
            _positive(),
            cfg,
        )
