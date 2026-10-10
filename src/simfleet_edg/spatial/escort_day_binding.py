"""Read frozen B2 proposals and person-purpose anchors; no drawing or refitting."""
from __future__ import annotations

import csv
import gzip
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path

from simfleet_edg.spatial.escort_partial_day_index import OriginalDay
from simfleet_edg.spatial.escort_target_anchor_extension import AnchorAssignment, read_core_stable

B0 = "B0_NO_LINK"
VARIANTS = (B0, *(f"B2_SRV{year}_HH{pct:03d}" for year in (2018, 2023)
                   for pct in (0, 25, 50, 75, 100)))


def read_csv_gz(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def frozen_anchors(core_root: Path, b2_a_root: Path, *, strict: bool = True
                   ) -> dict[tuple[str, str], AnchorAssignment]:
    """Merge references, not reselect locations; reject overlaps."""
    core = read_core_stable(core_root / "spatial_1/S_DIST/core_stable_locations_S_DIST_v1.csv.gz")
    sidecar = read_csv_gz(b2_a_root / "A/target_stable_anchor_extension_v1.csv.gz")
    if strict and len(sidecar) != 7621:
        raise ValueError("BLOCKED_ANCHOR_SIDECAR_CARDINALITY")
    for row in sidecar:
        key = (row["person_id"], row["purpose"])
        if key in core or row["origin"] != "SIDECAR":
            raise ValueError("BLOCKED_ANCHOR_IDENTITY_OR_OVERLAP")
        core[key] = AnchorAssignment(*key, row["location_id"],
                                     float(row["prior_aggregate_km"]), "SIDECAR")
    if strict and len(core) != 37676:
        raise ValueError("BLOCKED_ANCHOR_TOTAL_COUNT")
    return core


def read_proposals(path: Path, days: tuple[OriginalDay, ...], variant: str,
                   people: Mapping[str, str], eligible: Mapping[str, frozenset[str]],
                   anchors: Mapping[tuple[str, str], AnchorAssignment],
                   valid_locations: frozenset[str], *, strict: bool = True
                   ) -> dict[str, dict[str, str]]:
    """Check proposal event identity and completed links against immutable M1/M2/C.

    Unresolved original proposals remain typed, but a malformed *resolved*
    proposal is a fatal input-contract violation rather than a missing link.
    """
    if variant not in VARIANTS:
        raise ValueError("BLOCKED_VARIANT_ID")
    expected = {f"{d.row_id}:{t.trip_index}": (d, t) for d in days if d.has_escort
                for t in d.trips if t.destination_activity == "ESCORT"}
    if len(expected) != (18871 if strict else len(expected)):
        raise ValueError("BLOCKED_EVENT_IDENTITY_COUNT")
    records = read_csv_gz(path)
    if len(records) != len(expected):
        raise ValueError("BLOCKED_EVENT_CARDINALITY")
    seen: dict[str, dict[str, str]] = {}
    for row in records:
        event = row["event_id"]
        if event in seen or event not in expected or row["variant_id"] != variant:
            raise ValueError("BLOCKED_EVENT_DUPLICATE_OR_VARIANT")
        d, t = expected[event]
        if (row["row_id"] != d.row_id or int(row["trip_index"]) != t.trip_index
                or row["escort_person_id"] != d.person_id
                or row["escort_household_id"] != d.household_id
                or row["original_destination_activity"] != "ESCORT"
                or int(row["original_arrival_absolute_minute"]) != t.arrival_absolute_minute
                or int(row["original_departure_clock_minute"]) != t.departure_clock_minute):
            raise ValueError("BLOCKED_EVENT_FROZEN_IDENTITY")
        status = row["status"]
        if status == "RESOLVED_LOCATION_ONLY":
            target = row["target_person_id"]
            purpose = row["target_purpose"]
            key = (target, "WORK_COMMUTE" if purpose == "WORK" else purpose)
            thh = people.get(target)
            relation_scope = "HOUSEHOLD" if thh == d.household_id else "NONHOUSEHOLD"
            if (variant == B0 or purpose not in ("WORK", "EDUCATION")
                    or target == d.person_id or thh is None
                    or row["scope"] != relation_scope
                    or purpose not in eligible.get(target, frozenset())
                    or key not in anchors
                    or anchors[key].location_id != row["target_location_id"]
                    or row["target_location_id"] not in valid_locations):
                raise ValueError("BLOCKED_LINK_FROZEN_ANCHOR_CONTRACT")
        elif status not in {"UNRESOLVED_UNSUPPORTED_PURPOSE", "UNRESOLVED_NO_ELIGIBLE_PARTNER",
                            "UNRESOLVED_TARGET_ANCHOR", "UNRESOLVED_B0_NO_LINK"}:
            raise ValueError("BLOCKED_EVENT_UNKNOWN_STATUS")
        elif row["target_location_id"] or row["target_person_id"]:
            raise ValueError("BLOCKED_UNRESOLVED_CANNOT_HAVE_TARGET")
        if variant == B0 and status != "UNRESOLVED_B0_NO_LINK":
            raise ValueError("BLOCKED_B0_MUST_NOT_LINK")
        seen[event] = row
    if seen.keys() != expected.keys():
        raise ValueError("BLOCKED_EVENT_SET_MISMATCH")
    return seen


def by_day(proposals: Mapping[str, dict[str, str]]) -> dict[str, tuple[dict[str, str], ...]]:
    result: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in proposals.values():
        result[row["row_id"]].append(row)
    return {rid: tuple(sorted(rows, key=lambda r: int(r["trip_index"]))) for rid, rows in result.items()}
