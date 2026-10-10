"""Destination-location-only inheritance from frozen C LocationRefs."""
from __future__ import annotations

from simfleet_edg.canonical.mobility import LocationRef
from simfleet_edg.spatial.escort_target_anchor_extension import AnchorAssignment


def inherit_location(anchor: AnchorAssignment, locations: dict[str, LocationRef]) -> LocationRef:
    """Never create POI/coordinates; a binding is not observed co-travel."""
    if anchor.purpose not in {"EDUCATION", "WORK_COMMUTE"}:
        raise ValueError("Target HOME/other not sampled in local SrV experiment")
    try:
        return locations[anchor.location_id]
    except KeyError as exc:
        raise ValueError("Unresolvable frozen C LocationRef") from exc
