from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Iterable, Mapping, Sequence

ACTIVITIES = ("HOME", "WORK", "SHOPPING", "LEISURE")


def derive_uint64(
    master_seed: int,
    scenario_id: str,
    person_id: str,
    component_namespace: str,
    draw_index: int,
) -> int:
    payload = (
        f"{master_seed}|{scenario_id}|{person_id}|"
        f"{component_namespace}|{draw_index}"
    ).encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def uniform01(seed_u64: int) -> float:
    return (seed_u64 + 0.5) / 2**64


def normalize_pmf(
    pmf: Mapping[str, float],
    labels: Sequence[str] = ACTIVITIES,
) -> dict[str, float]:
    values = {label: float(pmf.get(label, 0.0)) for label in labels}
    if any((not math.isfinite(v) or v < 0.0) for v in values.values()):
        raise ValueError("PMF values must be finite and non-negative")
    total = sum(values.values())
    if total <= 0.0:
        raise ValueError("PMF must have positive mass")
    return {k: v / total for k, v in values.items()}


def categorical_draw(
    pmf: Mapping[str, float],
    u: float,
    labels: Sequence[str] = ACTIVITIES,
) -> str:
    if not 0.0 <= u < 1.0:
        raise ValueError("u must be in [0, 1)")
    p = normalize_pmf(pmf, labels)
    acc = 0.0
    for label in labels:
        acc += p[label]
        if u < acc:
            return label
    return labels[-1]


def weighted_log_loss(
    targets: Sequence[str],
    pmfs: Sequence[Mapping[str, float]],
    weights: Sequence[float],
) -> float:
    if not (len(targets) == len(pmfs) == len(weights)):
        raise ValueError("Targets, PMFs and weights must align")
    denom = sum(float(w) for w in weights)
    if denom <= 0.0:
        raise ValueError("Positive total weight required")
    loss = 0.0
    for target, pmf, weight in zip(targets, pmfs, weights, strict=True):
        p = normalize_pmf(pmf)
        prob = max(p.get(target, 0.0), 1e-15)
        loss += float(weight) * (-math.log(prob))
    return loss / denom


def weighted_shares(
    values: Sequence[str],
    weights: Sequence[float],
    categories: Sequence[str],
) -> dict[str, float]:
    if len(values) != len(weights):
        raise ValueError("Values and weights must align")
    total = sum(float(w) for w in weights)
    if total <= 0.0:
        raise ValueError("Positive total weight required")
    out = {c: 0.0 for c in categories}
    for value, weight in zip(values, weights, strict=True):
        if value not in out:
            raise ValueError(f"Unknown category: {value}")
        out[value] += float(weight)
    return {k: v / total for k, v in out.items()}


def tvd(
    observed: Mapping[str, float],
    generated: Mapping[str, float],
    categories: Iterable[str],
) -> float:
    return 0.5 * sum(
        abs(float(observed.get(c, 0.0)) - float(generated.get(c, 0.0)))
        for c in categories
    )


def absolute_return_home_error(
    observed_final: Sequence[str],
    generated_final: Sequence[str],
    weights: Sequence[float],
) -> float:
    if not (len(observed_final) == len(generated_final) == len(weights)):
        raise ValueError("Final states and weights must align")
    denom = sum(float(w) for w in weights)
    if denom <= 0:
        raise ValueError("Positive total weight required")
    obs = sum(
        float(w)
        for value, w in zip(observed_final, weights, strict=True)
        if value == "HOME"
    ) / denom
    gen = sum(
        float(w)
        for value, w in zip(generated_final, weights, strict=True)
        if value == "HOME"
    ) / denom
    return abs(gen - obs)


def validate_chain(states: Sequence[str], k: int) -> None:
    if len(states) != k + 1:
        raise ValueError("A chain with K transitions must have K+1 states")
    if k < 1:
        raise ValueError("Synthetic mobile chain requires K >= 1")


def paired_household_bootstrap(
    household_differences: Mapping[str, float],
    *,
    replicates: int,
    master_seed: int,
) -> tuple[float, float, float]:
    if not household_differences:
        raise ValueError("At least one household is required")
    ids = sorted(household_differences)
    rng = random.Random(master_seed)
    estimates: list[float] = []
    for _ in range(replicates):
        sample = [rng.choice(ids) for _ in ids]
        estimates.append(
            sum(household_differences[hh] for hh in sample) / len(sample)
        )
    estimates.sort()

    def quantile(q: float) -> float:
        pos = q * (len(estimates) - 1)
        lo = int(math.floor(pos))
        hi = int(math.ceil(pos))
        if lo == hi:
            return estimates[lo]
        frac = pos - lo
        return estimates[lo] * (1.0 - frac) + estimates[hi] * frac

    return quantile(0.025), quantile(0.5), quantile(0.975)
