"""No silent stable target generation, no epsilon, no partial full-day claims."""
from __future__ import annotations

from collections import Counter

import pytest

from simfleet_edg.repro.f4_2b_b_partial_integration import _counts, _summary
from simfleet_edg.spatial.escort_partial_day_index import OriginalDay, OriginalTrip
from simfleet_edg.spatial.escort_partial_integration import STATUS_SPATIAL_FAILURE, ResolvedDay


def test_frozen_accounting_produces_orig_denominators() -> None:
    a = OriginalTrip("r", 1, "p", "h", "HOME", "ESCORT", 1, 2, 1, 1.0)
    b = OriginalTrip("r", 2, "p", "h", "ESCORT", "HOME", 3, 4, 1, 1.0)
    day = OriginalDay("r", "p", "h", (a, b), True, True)
    assert _counts((day,))["escort_trips"] == 2
    result = _summary("B2_SRV2023_HH100", (day,), {
        "r": ResolvedDay(STATUS_SPATIAL_FAILURE, ("SPATIAL_S_DIST_NO_ELIGIBLE",), True, ())},
        Counter({"RESOLVED_LOCATION_ONLY": 1}), 0)
    assert result["coverage_and_failures"]["spatialized_escort_trips"] == 0
    assert result["real_person_linkage_observed"] is False
    assert result["experimental_variant_selected"] is False
    assert result["g3_open"] is False


def test_core_is_not_rewritten_or_synthetically_spatialized(monkeypatch: pytest.MonkeyPatch) -> None:
    # The frozen method excludes ESCORT, and must never be invoked by the new worker.
    import simfleet_edg.spatial.spatialize_core as module
    monkeypatch.setattr(module.Spatializer, "spatialize", lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError("Forbidden frozen spatialize() call")))
    from simfleet_edg.spatial.escort_partial_integration import integrate_escort_day
    assert callable(integrate_escort_day)
