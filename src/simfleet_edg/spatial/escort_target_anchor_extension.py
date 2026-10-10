"""Extend missing S_DIST person-purpose locations without editing frozen CORE."""
from __future__ import annotations

import csv
import gzip
from dataclasses import dataclass
from pathlib import Path

from simfleet_edg.spatial.escort_event_index import M2Index
from simfleet_edg.spatial.spatial_core_io import FrozenSupply
from simfleet_edg.spatial.spatialize_core import Spatializer

PURPOSE = {"EDUCATION": "EDUCATION", "WORK": "WORK_COMMUTE"}


@dataclass(frozen=True)
class AnchorAssignment:
    person_id: str
    purpose: str
    location_id: str
    prior_aggregate_km: float
    origin: str


def read_core_stable(path: Path) -> dict[tuple[str, str], AnchorAssignment]:
    answer: dict[tuple[str, str], AnchorAssignment] = {}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as file:
        for r in csv.DictReader(file):
            if r["policy"] != "S_DIST":
                raise ValueError("Frozen stable file not S_DIST")
            key = (r["person_id"], r["purpose"])
            if key in answer:
                raise ValueError("Duplicate frozen CORE stable anchor")
            answer[key] = AnchorAssignment(key[0], key[1], r["location_id"],
                                           float(r["prior_aggregate_km"]), "CORE")
    if len(answer) != 30055:
        raise ValueError("Frozen CORE stable anchor cardinality must equal 30055")
    return answer


def extend_stable_anchors(index: M2Index, supply: FrozenSupply,
                          core: dict[tuple[str, str], AnchorAssignment],
                          *, verify_all_overlap: bool = True) -> tuple[
                              dict[tuple[str, str], AnchorAssignment],
                              tuple[AnchorAssignment, ...]]:
    """Exact Spatializer._resolve(HOME, median HOME-origin prior, S_DIST).

    Recompute all overlapping stable keys to prove S_DIST identity, including
    the numeric stable median. Write ONLY newly missing keys to the sidecar.
    """
    spatializer = Spatializer(supply.indices, supply.locations, supply.anchors)
    expected = {(person, PURPOSE[purpose]) for person, purpose in index.stable_priors}
    if not set(core).issubset(expected):
        raise ValueError("BLOCKED_CONTRACT: frozen CORE stable identity absent in M2")
    all_anchors = dict(core)
    new_rows: list[AnchorAssignment] = []
    for person, purpose in sorted(index.stable_priors):
        mapped = PURPOSE[purpose]
        key = (person, mapped)
        prior = index.stable_priors[(person, purpose)]
        existing = core.get(key)
        if existing is not None and not verify_all_overlap:
            if existing.prior_aggregate_km != prior:
                raise ValueError("S_DIST CORE stable median mismatch")
            continue
        household = index.person_households[person]
        anchor = supply.anchors.get(household)
        if anchor is None:
            raise ValueError("M1 household missing frozen C HOME anchor")
        location = spatializer._resolve(anchor.location, prior, mapped, "S_DIST")
        if existing is not None:
            if existing.location_id != location.location_id or existing.prior_aggregate_km != prior:
                raise ValueError("BLOCKED_CONTRACT: S_DIST CORE overlap mismatch")
        else:
            result = AnchorAssignment(person, mapped, location.location_id, prior, "SIDECAR")
            new_rows.append(result)
            all_anchors[key] = result
    return all_anchors, tuple(new_rows)
