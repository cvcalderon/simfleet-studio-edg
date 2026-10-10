"""100k/325613 schema identity scaled down to deterministic fixtures."""
from __future__ import annotations

from simfleet_edg.canonical.mobility import LocationRef
from simfleet_edg.spatial.escort_partial_day_index import OriginalDay, OriginalTrip
from simfleet_edg.spatial.escort_partial_integration import (
    STATUS_RESOLVED,
    ResolvedDay,
    ResolvedTrip,
)
from simfleet_edg.spatial.escort_partial_ledger import day_rows, delta_rows, trip_rows


def fixture() -> tuple[tuple[OriginalDay, ...], dict[str, ResolvedDay]]:
    h = LocationRef("H", "HOME", 13, 52)
    e = LocationRef("E", "POI", 13.1, 52.1)
    ct = OriginalTrip("core", 1, "c", "h", "HOME", "HOME", 400, 410, 10, 1.0)
    xt = OriginalTrip("escort", 1, "x", "h", "HOME", "ESCORT", 400, 410, 10, 1.0)
    days = (OriginalDay("core", "c", "h", (ct,), False, True),
            OriginalDay("escort", "x", "h", (xt,), True, False))
    resolutions = {"escort": ResolvedDay(STATUS_RESOLVED, (), True, (
        ResolvedTrip(xt, h, e, "escort:1", "target", "CORE", 0.9, 0.1),))}
    return days, resolutions


def test_core_by_reference_and_append_only_escort() -> None:
    days, resolutions = fixture()
    day = list(day_rows(days, resolutions, "B2"))
    trips = list(trip_rows(days, resolutions, "B2", {("core", 1): ("H", "H")}))
    delta = list(delta_rows(days, resolutions, "B2"))
    assert len(day) == len(trips) == 2 and len(delta) == 1
    assert trips[0]["source_core_or_delta"] == "F4_2A_CORE_REFERENCE"
    assert trips[0]["origin_location_id"] == "H"
    assert trips[1]["destination_location_id"] == "E"
    assert delta[0]["event_id"] == "escort:1"


def test_unresolved_no_location_fabrication() -> None:
    days, resolutions = fixture()
    resolutions["escort"] = ResolvedDay("ESCORT_LINK_INCOMPLETE",
                                         ("UNRESOLVED_B0_NO_LINK",), False, ())
    trip = list(trip_rows(days, resolutions, "B0_NO_LINK", {("core", 1): ("H", "H")}))
    assert trip[1]["origin_location_id"] == ""
    assert trip[1]["destination_location_id"] == ""
    assert trip[1]["spatial_status"] == "ESCORT_UNSPATIALIZED"
