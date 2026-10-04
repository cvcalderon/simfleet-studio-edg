from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from simfleet_edg.population.six_plus import (
    derive_full_scale_h6_prior,
    materialize_h6_household_sizes,
    scale_h6_prior,
    uniform_weak_composition,
)
from simfleet_edg.population.zensus_controls import BERLIN_BEZIRK_CODES, NormalizedSource

SOURCE_H6 = [3974, 2397, 2150, 2323, 2216, 2215, 2679, 3590, 1602, 1596, 1430, 2356]
FULL_P6 = [34843, 22002, 20832, 23985, 16885, 16661, 23213, 28459, 13421, 12847, 11501, 18051]
EXPECTED_FULL_H6 = [3948, 2381, 2136, 2308, 2202, 2201, 2661, 3567, 1591, 1586, 1421, 2341]


def _source() -> NormalizedSource:
    frame = pd.DataFrame(
        {
            "GEOBZ1_code": BERLIN_BEZIRK_CODES,
            "GEOBZ1_label": [f"B{index}" for index in range(1, 13)],
            "HSHGR2_code": ["PERSON06UM"] * 12,
            "published_value": SOURCE_H6,
        }
    )
    return NormalizedSource("5000H-1001", Path("dummy.zip"), "dummy", frame)


def _full_cube() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "bezirk_code": BERLIN_BEZIRK_CODES,
            "household_size_code": ["PERSON06UM"] * 12,
            "fit_target_value": FULL_P6,
        }
    )


def _projected_s() -> pd.DataFrame:
    p6 = [100, 63, 58, 67, 47, 44, 65, 80, 39, 37, 32, 53]
    return pd.DataFrame(
        {
            "bezirk_code": BERLIN_BEZIRK_CODES,
            "household_size_code": ["PERSON06UM"] * 12,
            "projected_persons": p6,
            "reference_persons": [3532081] * 12,
            "scale_target_persons": [10000] * 12,
        }
    )


def test_full_scale_h6_prior_reproduces_frozen_anchor() -> None:
    prior = derive_full_scale_h6_prior(_source(), _full_cube())
    assert prior["full_scale_h6_prior"].tolist() == EXPECTED_FULL_H6
    assert int(prior["full_scale_h6_prior"].sum()) == 28343


def test_scaled_h6_prior_reproduces_s_anchor() -> None:
    full = derive_full_scale_h6_prior(_source(), _full_cube())
    scaled = scale_h6_prior(full, _projected_s(), scale_id="S")
    assert scaled["scale_h6_households"].tolist() == [11, 7, 6, 7, 6, 6, 8, 10, 4, 4, 4, 7]
    assert int(scaled["scale_h6_households"].sum()) == 80
    assert ((6 * scaled["scale_h6_households"]) <= scaled["projected_persons_6plus"]).all()


def test_uniform_weak_composition_is_seeded_and_exact() -> None:
    left = uniform_weak_composition(37, 9, seed=1234)
    right = uniform_weak_composition(37, 9, seed=1234)
    assert left.tolist() == right.tolist()
    assert len(left) == 9
    assert int(left.sum()) == 37
    assert (left >= 0).all()


def test_uniform_weak_composition_rejects_impossible_zero_household_case() -> None:
    with pytest.raises(ValueError):
        uniform_weak_composition(1, 0, seed=1)


def test_materialized_h6_sizes_preserve_households_and_persons() -> None:
    full = derive_full_scale_h6_prior(_source(), _full_cube())
    projected = _projected_s()
    scaled = scale_h6_prior(full, projected, scale_id="S")
    households, audit = materialize_h6_household_sizes(projected, scaled, scale_id="S")
    assert len(households) == 80
    assert int(households["generated_household_size"].sum()) == 685
    assert int(households["generated_household_size"].min()) >= 6
    assert audit.household_count_exact
    assert audit.person_count_exact
    assert audit.all_households_at_least_six
    assert set(households["donor_materialization_status"]) == {"DEFERRED_TO_IMPL_03"}
