"""Resolved event-specific target inheritance and B0 nonlinks."""
from __future__ import annotations

from pathlib import Path

import pytest

from simfleet_edg.spatial import escort_day_binding as binding
from simfleet_edg.spatial.escort_partial_day_index import OriginalDay, OriginalTrip
from simfleet_edg.spatial.escort_target_anchor_extension import AnchorAssignment


def fixture_days() -> tuple[OriginalDay, ...]:
    trip = OriginalTrip("r1", 1, "p1", "h1", "HOME", "ESCORT", 400, 410, 10, 1.0)
    return (OriginalDay("r1", "p1", "h1", (trip,), True, False),)


def event(status: str = "RESOLVED_LOCATION_ONLY") -> dict[str, str]:
    return {"event_id": "r1:1", "row_id": "r1", "trip_index": "1",
            "variant_id": "B2_SRV2023_HH000", "escort_person_id": "p1",
            "escort_household_id": "h1", "original_destination_activity": "ESCORT",
            "original_arrival_absolute_minute": "410", "original_departure_clock_minute": "400",
            "target_person_id": "p2", "target_purpose": "WORK", "target_location_id": "loc2",
            "scope": "NONHOUSEHOLD", "status": status}


def test_target_anchor_is_exact_and_event_specific(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(binding, "read_csv_gz", lambda path: [event()])
    answers = binding.read_proposals(Path("ignored"), fixture_days(), "B2_SRV2023_HH000",
                                     {"p1": "h1", "p2": "h2"},
                                     {"p2": frozenset({"WORK"})},
                                     {("p2", "WORK_COMMUTE"): AnchorAssignment(
                                         "p2", "WORK_COMMUTE", "loc2", 1.0, "CORE")},
                                     frozenset({"loc2"}), strict=False)
    assert answers["r1:1"]["target_person_id"] == "p2"


def test_self_link_fails_not_typed_as_uncertain(monkeypatch: pytest.MonkeyPatch) -> None:
    bad = event()
    bad["target_person_id"] = "p1"
    monkeypatch.setattr(binding, "read_csv_gz", lambda path: [bad])
    with pytest.raises(ValueError, match="BLOCKED_LINK_FROZEN_ANCHOR_CONTRACT"):
        binding.read_proposals(Path("ignored"), fixture_days(), "B2_SRV2023_HH000",
                               {"p1": "h1"}, {"p1": frozenset({"WORK"})},
                               {("p1", "WORK_COMMUTE"): AnchorAssignment(
                                   "p1", "WORK_COMMUTE", "loc2", 1.0, "CORE")},
                               frozenset({"loc2"}), strict=False)
