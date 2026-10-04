from __future__ import annotations

import pandas as pd

from simfleet_edg.population.age_projection import AGE_ZENSUS_11_SOURCE_CODES
from simfleet_edg.population.scale_projection import (
    largest_remainder_integerization,
    project_reconciled_cube,
)


def _toy_cube() -> pd.DataFrame:
    rows = []
    values = [0, 20, 18, 24, 20, 38]
    for household_size_code, value in zip(
        ["PERSON01", "PERSON02", "PERSON03", "PERSON04", "PERSON05", "PERSON06UM"],
        values,
        strict=True,
    ):
        rows.append(
            {
                "bezirk_code": "11000000000001",
                "bezirk_name": "Mitte",
                "age_zensus_11_source_code": AGE_ZENSUS_11_SOURCE_CODES[0],
                "sex_code": "GESM",
                "household_size_code": household_size_code,
                "fit_target_value": value,
            }
        )
    return pd.DataFrame(rows)


def test_largest_remainder_is_exact_and_deterministic() -> None:
    result = largest_remainder_integerization(
        weights=pd.Series([4, 3, 2, 1]).to_numpy(), total=7, keys=["a", "b", "c", "d"]
    )
    assert result.tolist() == [3, 2, 1, 1]
    assert int(result.sum()) == 7


def test_projection_hits_exact_target() -> None:
    projected, audit = project_reconciled_cube(_toy_cube(), scale_id="S", target_persons=60)
    assert int(projected["projected_persons"].sum()) == 60
    assert audit.all_bezirk_targets_exact


def test_projection_preserves_structural_zero() -> None:
    projected, audit = project_reconciled_cube(_toy_cube(), scale_id="S", target_persons=60)
    zero = projected[projected["household_size_code"] == "PERSON01"].iloc[0]
    assert int(zero["projected_persons"]) == 0
    assert audit.structural_zero_violations == 0


def test_projection_preserves_exact_size_divisibility() -> None:
    projected, audit = project_reconciled_cube(_toy_cube(), scale_id="S", target_persons=60)
    for household_size_code, size in [
        ("PERSON01", 1),
        ("PERSON02", 2),
        ("PERSON03", 3),
        ("PERSON04", 4),
        ("PERSON05", 5),
    ]:
        total = int(
            projected.loc[
                projected["household_size_code"] == household_size_code,
                "projected_persons",
            ].sum()
        )
        assert total % size == 0
    assert audit.divisibility_violations_sizes_1_to_5 == 0


def test_projection_is_input_order_invariant() -> None:
    cube = _toy_cube()
    left, _ = project_reconciled_cube(cube, scale_id="S", target_persons=61)
    right, _ = project_reconciled_cube(
        cube.sample(frac=1.0, random_state=17), scale_id="S", target_persons=61
    )
    columns = ["household_size_code", "projected_persons"]
    assert left[columns].reset_index(drop=True).equals(right[columns].reset_index(drop=True))
