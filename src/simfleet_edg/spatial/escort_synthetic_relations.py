"""Keyed, order-independent LOCAL-ONLY hypothetical escort association draws.

No co-travel/kinship observation; purpose priors are external descriptive
TRANSFER scenarios, while HH share and uniform partner choice are hypothetical.
"""
from __future__ import annotations

import bisect
import csv
import hashlib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from simfleet_edg.spatial.escort_event_index import EscortEvent, M2Index
from simfleet_edg.spatial.escort_target_anchor_extension import AnchorAssignment

NAMESPACE = "F4_2B_A_ESCORT_LINK_RNG_V1"
SEED = 20261007
PROVENANCE = "SYNTHETIC_HYPOTHETICAL_NOT_OBSERVED"


@dataclass(frozen=True)
class Variant:
    variant_id: str
    year: str
    p_household: float
    p_education: float
    p_work: float
    p_unsupported: float


def load_variants(path: Path) -> tuple[Variant, ...]:
    with path.open(newline="", encoding="utf-8") as f:
        raw = list(csv.DictReader(f))
    items = [Variant(r["variant_id"], r["year"], float(r["p_household_hypothesis"]),
                     float(r["p_education_src_transfer"]),
                     float(r["p_work_src_transfer"]),
                     float(r["p_unresolved_unsupported_src_transfer"])) for r in raw]
    if len(items) != 10 or len({v.variant_id for v in items}) != 10:
        raise ValueError("Exactly 10 distinct MAIN-frozen B2 variants required")
    for v in items:
        expect = (.739, .025, .236) if v.year == "2018" else (.765, .023, .212)
        if v.year not in {"2018", "2023"} or (v.p_education, v.p_work, v.p_unsupported) != expect:
            raise ValueError("External-descriptive SrV prior differs from freeze")
        if v.p_household not in {0.0, 0.25, 0.5, 0.75, 1.0}:
            raise ValueError("Unregistered hypothetical household share")
        if v.variant_id != f"B2_SRV{v.year}_HH{int(v.p_household*100):03d}":
            raise ValueError("Noncanonical frozen variant identity")
    return tuple(items)


def keyed_uniform(scenario: str, day: str, event: str, variant: str,
                  prior_sha: str, purpose_label: str, stream: str) -> float:
    """First 53 high bits of SHA-256 as IEEE-754 exact n/2**53, in [0,1)."""
    if stream not in {"PURPOSE", "SCOPE", "PARTNER"}:
        raise ValueError("Unknown RNG draw stream")
    payload = "|".join((NAMESPACE, str(SEED), scenario, day, event, variant,
                        prior_sha, purpose_label, stream)).encode("utf-8")
    return (int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") >> 11) / 2**53


def draw_purpose(u: float, v: Variant) -> str:
    if not 0.0 <= u < 1.0:
        raise ValueError("Uniform outside [0,1)")
    if u < v.p_education:
        return "EDUCATION"
    if u < v.p_education + v.p_work:
        return "WORK"
    return "UNSUPPORTED_PURPOSE"


class PartnerPools:
    """Sorted eligible M1 ID arrays, O(log n + household-size) draw.

    Construct once per purpose; never exhaustively scan 100k people per event.
    """

    def __init__(self, idx: M2Index,
                 anchors: dict[tuple[str, str], AnchorAssignment]) -> None:
        self.homes = idx.person_households
        self.raw: dict[str, tuple[str, ...]] = {}
        self.raw_hh_counts: dict[str, dict[str, int]] = {}
        self.raw_sets: dict[str, frozenset[str]] = {}
        self.resolved: dict[str, tuple[str, ...]] = {}
        self.by_hh: dict[str, dict[str, tuple[str, ...]]] = {}
        self._excluded_positions: dict[tuple[str, str], tuple[int, ...]] = {}
        for purpose in ("EDUCATION", "WORK"):
            label = "WORK_COMMUTE" if purpose == "WORK" else purpose
            raw = sorted(p for p, acts in idx.activities.items() if purpose in acts)
            resolved = sorted(p for p in raw if (p, label) in anchors)
            by_hh: dict[str, list[str]] = defaultdict(list)
            raw_hh: dict[str, int] = defaultdict(int)
            for p in raw:
                raw_hh[self.homes[p]] += 1
            self.raw_hh_counts[purpose] = dict(raw_hh)
            excluded: dict[str, list[int]] = defaultdict(list)
            for i, p in enumerate(resolved):
                hh = self.homes[p]
                by_hh[hh].append(p)
                excluded[hh].append(i)
            self.raw[purpose], self.resolved[purpose] = tuple(raw), tuple(resolved)
            self.raw_sets[purpose] = frozenset(raw)
            self.by_hh[purpose] = {h: tuple(v) for h, v in by_hh.items()}
            self._excluded_positions.update({(purpose, h): tuple(v) for h, v in excluded.items()})

    def _population_counts(self, purpose: str, household: str, own: str,
                           selected_household: bool) -> tuple[int, int]:
        raw = self.raw[purpose]
        resolved = self.resolved[purpose]
        count_hh = self.raw_hh_counts[purpose].get(household, 0)
        if selected_household:
            raw_count = count_hh - int(own in self.raw_sets[purpose] and self.homes[own] == household)
            eligible_count = len(self.by_hh[purpose].get(household, ())) - int(own in self.by_hh[purpose].get(household, ()))
        else:
            raw_count = len(raw) - count_hh
            eligible_count = len(resolved) - len(self.by_hh[purpose].get(household, ()))
        return raw_count, eligible_count

    def pick(self, purpose: str, own: str, household: str,
             hh_scope: bool, u: float) -> tuple[str | None, str]:
        """Uniform over feasible, no fallback. Raw counts are pre-indexable."""
        if not 0 <= u < 1:
            raise ValueError("Uniform outside [0,1)")
        if purpose not in self.resolved:
            raise ValueError("Unsupported target purpose")
        raw_count, eligible_count = self._population_counts(purpose, household, own, hh_scope)
        if eligible_count == 0:
            return (None, "UNRESOLVED_TARGET_ANCHOR" if raw_count else "UNRESOLVED_NO_ELIGIBLE_PARTNER")
        k = int(eligible_count * u)
        all_ids = self.resolved[purpose]
        if hh_scope:
            candidates = self.by_hh[purpose].get(household, ())
            if own not in candidates:
                return candidates[k], "RESOLVED_LOCATION_ONLY"
            pos = bisect.bisect_left(candidates, own)
            selected = k if k < pos else k + 1
            return candidates[selected], "RESOLVED_LOCATION_ONLY"
        # Select k-th complement after removing this household's global indices.
        excluded = self._excluded_positions.get((purpose, household), ())
        j = k
        for position in excluded:
            if position <= j:
                j += 1
            else:
                break
        assert j < len(all_ids) and self.homes[all_ids[j]] != household
        return all_ids[j], "RESOLVED_LOCATION_ONLY"


def propose(event: EscortEvent, variant: Variant | None, pools: PartnerPools,
            anchors: dict[tuple[str, str], AnchorAssignment], *,
            scenario: str, day: str, prior_sha: str) -> dict[str, str]:
    """Always one row per original ESCORT event, including unresolved cases."""
    result = {"variant_id": "B0_NO_LINK" if variant is None else variant.variant_id,
              "row_id": event.row_id, "trip_index": str(event.trip_index),
              "event_id": event.event_id, "escort_person_id": event.person_id,
              "escort_household_id": event.household_id,
              "original_destination_activity": "ESCORT", "original_arrival_absolute_minute": str(event.arrival_absolute_minute),
              "original_departure_clock_minute": str(event.departure_clock_minute),
              "target_purpose": "", "scope": "", "target_person_id": "", "target_location_id": "",
              "status": "UNRESOLVED_B0_NO_LINK", "evidence_class": PROVENANCE,
              "source_prior_sha256": prior_sha, "draw_stream_namespace": NAMESPACE,
              "temporal_claim": "LOCATION_ONLY_NO_CO_TRAVEL_INFERENCE"}
    if variant is None:
        return result
    u_purpose = keyed_uniform(scenario, day, event.event_id, variant.variant_id, prior_sha, "NA", "PURPOSE")
    purpose = draw_purpose(u_purpose, variant)
    result["target_purpose"] = purpose
    if purpose == "UNSUPPORTED_PURPOSE":
        result["status"] = "UNRESOLVED_UNSUPPORTED_PURPOSE"
        return result
    u_scope = keyed_uniform(scenario, day, event.event_id, variant.variant_id, prior_sha, purpose, "SCOPE")
    household_scope = u_scope < variant.p_household
    result["scope"] = "HOUSEHOLD" if household_scope else "NONHOUSEHOLD"
    u_partner = keyed_uniform(scenario, day, event.event_id, variant.variant_id, prior_sha, purpose, "PARTNER")
    target, status = pools.pick(purpose, event.person_id, event.household_id, household_scope, u_partner)
    result["status"] = status
    if target is None:
        return result
    key = (target, "WORK_COMMUTE" if purpose == "WORK" else purpose)
    if key not in anchors:
        raise ValueError("Eligible M2 target missing accepted stable anchor")
    result["target_person_id"] = target
    result["target_location_id"] = anchors[key].location_id
    return result
