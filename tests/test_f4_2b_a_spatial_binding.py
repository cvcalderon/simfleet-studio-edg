from __future__ import annotations

import pytest

from simfleet_edg.canonical.mobility import LocationRef
from simfleet_edg.spatial.escort_location_binding import inherit_location
from simfleet_edg.spatial.escort_target_anchor_extension import AnchorAssignment


def test_locationref_inherited_not_recreated_or_travel_claim() -> None:
    location = LocationRef("src", "POINT", 13.4, 52.5)
    anchor = AnchorAssignment("p", "EDUCATION", "src", 2.0, "SIDECAR")
    assert inherit_location(anchor, {"src": location}) is location
    with pytest.raises(ValueError, match="Unresolvable"):
        inherit_location(anchor, {})
    with pytest.raises(ValueError, match="HOME/other"):
        inherit_location(AnchorAssignment("p", "HOME", "src", 1, "SIDECAR"), {"src": location})
