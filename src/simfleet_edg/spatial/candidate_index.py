"""Purpose-specific exact bounding-box branch-and-bound spatial candidate index.

The admissible upper bound is max C_dist attained in [d_min, d_max] by an
ideal point on the box. S_ATTR upper bound additionally multiplies by the
largest actual weight in the subtree (<=1.5). Strict < pruning preserves ties.
Only leaves are materialized per query; never a demand-by-supply matrix.
"""
from __future__ import annotations

import heapq
import math
from collections.abc import Iterable
from dataclasses import dataclass

from simfleet_edg.spatial.candidate_policies import (
    Choice,
    Policy,
    better,
    check_prior,
    compatibility,
)


@dataclass(frozen=True, slots=True)
class Candidate:
    location_id: str
    x: float  # EPSG:25833 metric metres
    y: float
    area_weight: float = 1.0

    def __post_init__(self) -> None:
        if not self.location_id or not all(map(math.isfinite, (self.x, self.y))):
            raise ValueError("Invalid candidate identity/metric coordinates")
        if not math.isfinite(self.area_weight) or not 0.5 <= self.area_weight <= 1.5:
            raise ValueError("Invalid frozen area weight")


@dataclass(slots=True)
class _Node:
    xmin: float
    xmax: float
    ymin: float
    ymax: float
    weight_max: float
    left: _Node | None
    right: _Node | None
    entries: tuple[Candidate, ...]


def _build(candidates: list[Candidate], leaf_size: int) -> _Node:
    x0 = min(c.x for c in candidates)
    x1 = max(c.x for c in candidates)
    y0 = min(c.y for c in candidates)
    y1 = max(c.y for c in candidates)
    w = max(c.area_weight for c in candidates)
    if len(candidates) <= leaf_size:
        return _Node(x0, x1, y0, y1, w, None, None, tuple(candidates))
    key = (lambda c: (c.x, c.location_id)) if x1 - x0 >= y1 - y0 else (lambda c: (c.y, c.location_id))
    ordered = sorted(candidates, key=key)
    middle = len(ordered) // 2
    left, right = _build(ordered[:middle], leaf_size), _build(ordered[middle:], leaf_size)
    return _Node(x0, x1, y0, y1, w, left, right, ())


def _range_m(node: _Node, x: float, y: float) -> tuple[float, float]:
    near_x = max(node.xmin - x, 0.0, x - node.xmax)
    near_y = max(node.ymin - y, 0.0, y - node.ymax)
    far_x = max(abs(node.xmin - x), abs(node.xmax - x))
    far_y = max(abs(node.ymin - y), abs(node.ymax - y))
    return math.hypot(near_x, near_y), math.hypot(far_x, far_y)


def _upper(node: _Node, x: float, y: float, p: float, policy: Policy) -> float:
    dmin_m, dmax_m = _range_m(node, x, y)
    if policy == "S_NEAR":
        return math.nextafter(-dmin_m / 1000.0, math.inf)
    lower, upper = dmin_m / 1000.0, dmax_m / 1000.0
    if lower <= p <= upper:
        ub = 1.0
    elif upper < p:
        ub = upper / p
    else:
        ub = p / lower
    return math.nextafter(ub * (node.weight_max if policy == "S_ATTR" else 1.0), math.inf)


class CandidateIndex:
    """Exact point index; each instance is restricted to one eligible purpose."""

    def __init__(self, candidates: Iterable[Candidate], *, leaf_size: int = 24) -> None:
        if leaf_size < 1:
            raise ValueError("leaf_size must be positive")
        self.candidates = tuple(sorted(candidates, key=lambda c: c.location_id))
        if not self.candidates or len({c.location_id for c in self.candidates}) != len(self.candidates):
            raise ValueError("A purpose must have distinct, nonempty candidate identifiers")
        self.root = _build(list(self.candidates), leaf_size)
        self.last_visited = 0

    def choose(self, x: float, y: float, prior_km: float, policy: Policy) -> Choice:
        p = check_prior(prior_km)
        if not all(map(math.isfinite, (x, y))):
            raise ValueError("Origin projected coordinates must be finite")
        best: Choice | None = None
        visited = 0
        counter = 0
        queue: list[tuple[float, int, _Node]] = [(-_upper(self.root, x, y, p, policy), 0, self.root)]
        while queue:
            neg_bound, _, node = heapq.heappop(queue)
            current = None if best is None else (
                -best.distance_km if policy == "S_NEAR" else
                best.compatibility * (best.area_weight if policy == "S_ATTR" else 1.0)
            )
            # Strict inequality: equal-score candidates may win on secondary ties.
            if current is not None and -neg_bound < current:
                continue
            if node.entries:
                for item in node.entries:
                    visited += 1
                    d = math.hypot(item.x - x, item.y - y) / 1000.0
                    cand = Choice(item.location_id, d, compatibility(d, p), item.area_weight)
                    if better(cand, best, policy, p):
                        best = cand
            else:
                for branch in (node.left, node.right):
                    if branch is not None:
                        counter += 1
                        heapq.heappush(queue, (-_upper(branch, x, y, p, policy), counter, branch))
        self.last_visited = visited
        if best is None:
            raise AssertionError("Empty candidate index")
        return best

    def brute_force(self, x: float, y: float, p: float, policy: Policy) -> Choice:
        """Independent exhaustive oracle used by tests, never official search."""
        check_prior(p)
        best: Choice | None = None
        for item in self.candidates:
            d = math.hypot(item.x - x, item.y - y) / 1000.0
            choice = Choice(item.location_id, d, compatibility(d, p), item.area_weight)
            if better(choice, best, policy, p):
                best = choice
        if best is None:
            raise AssertionError("Empty candidate index")
        return best
