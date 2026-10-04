"""Frozen structural completion for top-coded 6+ private households."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from typing import Final

import numpy as np
import pandas as pd

from simfleet_edg.population.zensus_controls import BERLIN_BEZIRK_CODES, NormalizedSource

POLICY_ID: Final[str] = "H6_COMPLETION_V1"
SIZE_METHOD_ID: Final[str] = "UNIFORM_WEAK_COMPOSITION_V1"
MASTER_SEED: Final[int] = 20261004
RHO_MULTI_2_5: Final[Decimal] = Decimal("0.993516178214743")
FULL_SCALE_H6_TOTAL: Final[int] = 28_343


@dataclass(frozen=True)
class SixPlusAudit:
    scale_id: str
    household_count: int
    person_count: int
    minimum_household_size: int
    maximum_household_size: int
    household_count_exact: bool
    person_count_exact: bool
    all_households_at_least_six: bool


def _round_half_up_ratio(numerator: int, denominator: int) -> int:
    quotient, remainder = divmod(int(numerator), int(denominator))
    return quotient + int(2 * remainder >= denominator)


def _seed(master_seed: int, scale_id: str, bezirk_code: str, substream_key: str) -> int:
    payload = f"{master_seed}|{substream_key}|{scale_id}|{bezirk_code}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big", signed=False)


def _constrained_largest_remainder_decimal(
    quotas: list[Decimal],
    total: int,
    caps: list[int],
    keys: list[str],
) -> np.ndarray:
    if not (len(quotas) == len(caps) == len(keys)):
        raise ValueError("quota/cap/key length mismatch")
    base = np.array(
        [int(quota.to_integral_value(rounding=ROUND_FLOOR)) for quota in quotas], dtype=int
    )
    cap_array = np.asarray(caps, dtype=int)
    base = np.minimum(base, cap_array)
    remaining = int(total - int(base.sum()))
    if remaining < 0:
        raise ValueError("Capped floors already exceed target total")
    while remaining:
        eligible = [index for index in range(len(base)) if base[index] < cap_array[index]]
        if not eligible:
            raise ValueError("6+ household-count target infeasible under person-count caps")
        index = min(
            eligible,
            key=lambda item: (-(quotas[item] - Decimal(int(base[item]))), str(keys[item])),
        )
        base[index] += 1
        remaining -= 1
    return base


def derive_full_scale_h6_prior(
    household_source: NormalizedSource,
    full_cube: pd.DataFrame,
) -> pd.DataFrame:
    """Derive the frozen model household-count prior from 5000H and rho_multi_2_5."""
    frame = household_source.frame
    six = frame[frame["HSHGR2_code"] == "PERSON06UM"].copy()
    six = six.sort_values("GEOBZ1_code").reset_index(drop=True)
    if tuple(six["GEOBZ1_code"].astype(str)) != BERLIN_BEZIRK_CODES:
        raise ValueError("5000H 6+ prior does not cover the 12 Berlin Bezirke exactly")

    p6 = (
        full_cube[full_cube["household_size_code"] == "PERSON06UM"]
        .groupby("bezirk_code", sort=True)["fit_target_value"]
        .sum()
        .reindex(BERLIN_BEZIRK_CODES)
    )
    if p6.isna().any():
        raise ValueError("Full person-domain cube lacks a 6+ target for a Berlin Bezirk")

    source_counts = six["published_value"].astype(int).tolist()
    quotas = [Decimal(value) * RHO_MULTI_2_5 for value in source_counts]
    caps = (p6.astype(int) // 6).tolist()
    allocated = _constrained_largest_remainder_decimal(
        quotas, FULL_SCALE_H6_TOTAL, caps, list(BERLIN_BEZIRK_CODES)
    )
    return pd.DataFrame(
        {
            "bezirk_code": list(BERLIN_BEZIRK_CODES),
            "bezirk_name": six["GEOBZ1_label"].astype(str).tolist(),
            "source_households_6plus_5000H": source_counts,
            "person_target_6plus_full": p6.astype(int).tolist(),
            "rho_multi_2_5": [str(RHO_MULTI_2_5)] * len(six),
            "full_scale_h6_prior": allocated.astype(int),
            "role": ["MODEL_FIXED_STRUCTURAL_TARGET_NOT_SOURCE_HARD"] * len(six),
        }
    )


def scale_h6_prior(
    full_prior: pd.DataFrame,
    projected_cube: pd.DataFrame,
    *,
    scale_id: str,
) -> pd.DataFrame:
    """Scale the frozen 6+ household prior while enforcing 6*H6 <= P6 by Bezirk."""
    reference_persons = int(projected_cube["reference_persons"].iloc[0])
    target_persons = int(projected_cube["scale_target_persons"].iloc[0])
    target_h6 = _round_half_up_ratio(FULL_SCALE_H6_TOTAL * target_persons, reference_persons)

    prior = full_prior.sort_values("bezirk_code").reset_index(drop=True)
    p6 = (
        projected_cube[projected_cube["household_size_code"] == "PERSON06UM"]
        .groupby("bezirk_code", sort=True)["projected_persons"]
        .sum()
        .reindex(prior["bezirk_code"])
    )
    if p6.isna().any():
        raise ValueError("Projected cube lacks a 6+ person target for a Bezirk")

    denominator = Decimal(reference_persons)
    quotas = [
        Decimal(int(value)) * Decimal(target_persons) / denominator
        for value in prior["full_scale_h6_prior"]
    ]
    caps = (p6.astype(int) // 6).tolist()
    allocated = _constrained_largest_remainder_decimal(
        quotas,
        target_h6,
        caps,
        prior["bezirk_code"].astype(str).tolist(),
    )
    out = prior[["bezirk_code", "bezirk_name", "full_scale_h6_prior"]].copy()
    out["scale_id"] = scale_id
    out["scale_target_persons"] = target_persons
    out["projected_persons_6plus"] = p6.astype(int).tolist()
    out["scale_h6_households"] = allocated.astype(int)
    out["scale_h6_target_berlin"] = target_h6
    out["cap_households_from_persons"] = (p6.astype(int) // 6).tolist()
    return out


def uniform_weak_composition(extras: int, households: int, *, seed: int) -> np.ndarray:
    """Sample uniformly from all weak compositions via an exact stars-and-bars draw."""
    if extras < 0 or households < 0:
        raise ValueError("extras and households must be nonnegative")
    if households == 0:
        if extras:
            raise ValueError("Cannot allocate extras into zero households")
        return np.array([], dtype=int)
    if households == 1:
        return np.array([extras], dtype=int)
    rng = np.random.default_rng(seed)
    bars = np.sort(
        rng.choice(np.arange(1, extras + households), size=households - 1, replace=False)
    )
    points = np.concatenate(([0], bars, [extras + households]))
    result = np.diff(points) - 1
    if len(result) != households or int(result.sum()) != extras or np.any(result < 0):
        raise AssertionError("Internal weak-composition invariant failure")
    return result.astype(int)


def materialize_h6_household_sizes(
    projected_cube: pd.DataFrame,
    scaled_prior: pd.DataFrame,
    *,
    scale_id: str,
    master_seed: int = MASTER_SEED,
) -> tuple[pd.DataFrame, SixPlusAudit]:
    """Materialize only latent 6+ household sizes; donor/template realization is IMPL-03."""
    rows: list[dict[str, object]] = []
    prior = scaled_prior.sort_values("bezirk_code").reset_index(drop=True)
    for record in prior.itertuples(index=False):
        persons = int(record.projected_persons_6plus)
        households = int(record.scale_h6_households)
        extras = persons - 6 * households
        if extras < 0:
            raise ValueError(f"Infeasible 6+ prior for Bezirk {record.bezirk_code}")
        generation_seed = _seed(
            master_seed, scale_id, str(record.bezirk_code), "H6_SIZE_COMPOSITION"
        )
        composition = uniform_weak_composition(extras, households, seed=generation_seed)
        for index, extra in enumerate(composition, start=1):
            rows.append(
                {
                    "scale_id": scale_id,
                    "bezirk_code": str(record.bezirk_code),
                    "bezirk_name": str(record.bezirk_name),
                    "h6_household_id": f"H6-{scale_id}-{record.bezirk_code}-{index:06d}",
                    "generated_household_size": 6 + int(extra),
                    "base_members": 6,
                    "extra_members": int(extra),
                    "household_size_topcoded": True,
                    "household_size_generated": True,
                    "six_plus_completion_policy": POLICY_ID,
                    "size_generation_method": SIZE_METHOD_ID,
                    "generation_seed": generation_seed,
                    "donor_materialization_status": "DEFERRED_TO_IMPL_03",
                }
            )

    households_frame = pd.DataFrame(rows)
    expected_households = int(prior["scale_h6_households"].sum())
    expected_persons = int(prior["projected_persons_6plus"].sum())
    observed_persons = int(households_frame["generated_household_size"].sum())
    minimum = int(households_frame["generated_household_size"].min()) if len(rows) else 0
    maximum = int(households_frame["generated_household_size"].max()) if len(rows) else 0
    audit = SixPlusAudit(
        scale_id=scale_id,
        household_count=int(len(households_frame)),
        person_count=observed_persons,
        minimum_household_size=minimum,
        maximum_household_size=maximum,
        household_count_exact=int(len(households_frame)) == expected_households,
        person_count_exact=observed_persons == expected_persons,
        all_households_at_least_six=bool((households_frame["generated_household_size"] >= 6).all()),
    )
    return households_frame, audit
