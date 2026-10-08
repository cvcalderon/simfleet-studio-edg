from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from simfleet_edg.demand.runtime_generator import (
    M3_ACTIVITY_VOCABULARY,
    project_m2_activity_frames,
)


def _inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    days = pd.DataFrame([
        {"row_id": "r1", "trip_count": 3, "final_activity": "PRIVATE_ERRAND"},
        {"row_id": "r2", "trip_count": 0, "final_activity": ""},
        {"row_id": "r3", "trip_count": 1, "final_activity": "OTHER"},
    ])
    trips = pd.DataFrame([
        {"row_id": "r1", "trip_index": 1, "origin_activity": "HOME", "destination_activity": "PRIVATE_ERRAND"},
        {"row_id": "r1", "trip_index": 2, "origin_activity": "PRIVATE_ERRAND", "destination_activity": "SHOPPING"},
        {"row_id": "r1", "trip_index": 3, "origin_activity": "SHOPPING", "destination_activity": "PRIVATE_ERRAND"},
        {"row_id": "r3", "trip_index": 1, "origin_activity": "HOME", "destination_activity": "OTHER"},
    ])
    return days, trips


def test_projection_synchronized_and_raw_evidence_unchanged() -> None:
    days, trips = _inputs()
    raw_days, raw_trips = days.copy(deep=True), trips.copy(deep=True)
    result_days, result_trips, audit, counts = project_m2_activity_frames(days, trips)
    assert result_trips["origin_activity"].tolist() == ["HOME", "OTHER", "SHOPPING", "HOME"]
    assert result_trips["destination_activity"].tolist() == ["OTHER", "SHOPPING", "OTHER", "OTHER"]
    assert result_days["final_activity"].tolist() == ["OTHER", "", "OTHER"]
    assert counts["raw_private_errand_origin_rows"] == 1
    assert counts["raw_private_errand_destination_rows"] == 2
    assert counts["raw_private_errand_final_activity_days"] == 1
    assert counts["affected_person_days"] == 1
    assert len(audit) == 7
    assert set(result_trips["origin_activity"]).issubset(M3_ACTIVITY_VOCABULARY)
    assert set(result_trips["destination_activity"]).issubset(M3_ACTIVITY_VOCABULARY)
    pd.testing.assert_frame_equal(days, raw_days)
    pd.testing.assert_frame_equal(trips, raw_trips)
    # SHA-256 is stable under input reordering because audit has a stable order.
    rdays, rtrips, other_audit, _ = project_m2_activity_frames(
        days.iloc[::-1].reset_index(drop=True), trips.iloc[::-1].reset_index(drop=True)
    )
    assert audit.to_csv(index=False, lineterminator="\n") == other_audit.to_csv(index=False, lineterminator="\n")
    assert set(rdays["final_activity"]) == {"", "OTHER"}
    assert len(rtrips) == len(trips)


@pytest.mark.parametrize("bad", ["PRIVATE_RESEARCH", "UNSEEN", "", None])
def test_unknown_label_hard_fails(bad: object) -> None:
    days, trips = _inputs()
    trips.loc[0, "destination_activity"] = bad
    with pytest.raises(ValueError, match="(Unmapped M2|Invalid M2)"):
        project_m2_activity_frames(days, trips)


def test_144_raw_private_errand_destinations_regression() -> None:
    days = pd.DataFrame([{"row_id": f"r{i:03d}", "trip_count": 1, "final_activity": "PRIVATE_ERRAND"} for i in range(144)])
    trips = pd.DataFrame([
        {"row_id": f"r{i:03d}", "trip_index": 1, "origin_activity": "HOME", "destination_activity": "PRIVATE_ERRAND"}
        for i in range(144)
    ])
    _, projected, audit, counts = project_m2_activity_frames(days, trips)
    assert counts["raw_private_errand_destination_rows"] == 144
    assert counts["raw_private_errand_final_activity_days"] == 144
    assert set(projected["destination_activity"]) == {"OTHER"}
    assert (audit["raw_destination_activity"] == "PRIVATE_ERRAND").sum() == 144


def test_main_bridge_config_and_vocabulary() -> None:
    import yaml
    root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load((root / "configs/f4/f4_1d_runtime_taxonomy_bridge_v1.yaml").read_text())
    assert config["projection"] == {"PRIVATE_ERRAND": "OTHER"}
    assert set(config["runtime_vocabulary"]) == M3_ACTIVITY_VOCABULARY
    assert config["downstream_authorized"] is False
