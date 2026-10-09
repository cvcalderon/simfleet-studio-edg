"""Frozen deterministic F4.2a policies; never estimate route or realized travel."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

Policy = Literal["S_NEAR", "S_DIST", "S_ATTR"]
POLICIES: tuple[Policy, ...] = ("S_NEAR", "S_DIST", "S_ATTR")


def check_prior(prior_km: float) -> float:
    p = float(prior_km)
    if not math.isfinite(p) or p <= 0:
        raise ValueError("distance_prior_km must be strictly positive and finite")
    return p


def check_distance(distance_km: float) -> float:
    d = float(distance_km)
    if not math.isfinite(d) or d < 0:
        raise ValueError("spatial distance must be nonnegative and finite")
    return d


def compatibility(distance_km: float, prior_km: float) -> float:
    d, p = check_distance(distance_km), check_prior(prior_km)
    if d == 0:
        return 0.0
    return min(d / p, p / d)


def abs_log_ratio(distance_km: float, prior_km: float) -> float:
    d, p = check_distance(distance_km), check_prior(prior_km)
    return math.inf if d == 0 else abs(math.log(d) - math.log(p))


@dataclass(frozen=True, slots=True)
class Choice:
    location_id: str
    distance_km: float
    compatibility: float
    area_weight: float = 1.0


def ranking(choice: Choice, policy: Policy, prior_km: float) -> tuple[float, ...]:
    """Numeric components only; location_id is separate lexicographic final tie."""
    d = choice.distance_km
    p = check_prior(prior_km)
    if policy == "S_NEAR":
        return (-d,)
    c = choice.compatibility
    tie = (float(d <= p), -abs(d - p))
    if policy == "S_DIST":
        return (c, *tie)
    if policy == "S_ATTR":
        return (c * choice.area_weight, c, *tie)
    raise ValueError(f"Unrecognized policy: {policy}")


def better(candidate: Choice, incumbent: Choice | None, policy: Policy, p: float) -> bool:
    if incumbent is None:
        return True
    a, b = ranking(candidate, policy, p), ranking(incumbent, policy, p)
    return a > b or (a == b and candidate.location_id < incumbent.location_id)


def attractive_midrank_weights(areas: dict[str, float | None]) -> dict[str, float]:
    """Purpose-specific area midranks; equal positive polygon areas share midrank.

    Point or missing areas are neutral 1.0; ties get average 1-based rank.
    No canonical capacity/attractiveness field is modified.
    """
    valid = sorted(
        ((float(area), loc_id) for loc_id, area in areas.items()
         if area is not None and math.isfinite(float(area)) and float(area) > 0),
        key=lambda item: (item[0], item[1]),
    )
    n = len(valid)
    weights = {ident: 1.0 for ident in areas}
    i = 0
    while i < n:
        j = i + 1
        while j < n and valid[j][0] == valid[i][0]:
            j += 1
        rank = ((i + 1) + j) / 2.0
        weight = 0.5 + (rank - 0.5) / n
        for _, ident in valid[i:j]:
            weights[ident] = weight
        i = j
    return weights


def extended_metrics(errors: list[float]) -> dict[str, str | float | int]:
    """Extended-real mean, median and nearest-rank p90 with explicit INF."""
    if not errors:
        raise ValueError("No paired mobile trips: cannot evaluate candidate")
    if any(math.isnan(x) or x < 0 for x in errors):
        raise ValueError("Invalid distance diagnostic")
    ordered = sorted(errors)
    n = len(ordered)
    med = ((ordered[(n - 1) // 2] + ordered[n // 2]) / 2.0
           if n % 2 == 0 else ordered[n // 2])
    # Both central terms may be INF: extended-real arithmetic is defined.
    mean = math.inf if math.isinf(ordered[-1]) else math.fsum(ordered) / n
    p90 = ordered[math.ceil(0.9 * n) - 1]
    def render(x: float) -> str | float:
        return "INF" if math.isinf(x) else x
    return {"count": n, "inf_count": sum(math.isinf(x) for x in ordered),
            "median": render(med), "mean": render(mean), "p90": render(p90)}


def preregistered_promotion(near: dict[str, str | float | int],
                            dist: dict[str, str | float | int]) -> bool:
    """Compare extended real values, never post-hoc improve a broken metric."""
    def value(v: str | float | int) -> float:
        return math.inf if v == "INF" else float(v)
    return all(value(dist[name]) <= value(near[name]) for name in ("median", "mean", "p90"))
