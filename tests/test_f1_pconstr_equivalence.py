from __future__ import annotations

import pandas as pd

from simfleet_edg.population.equivalence import (
    CELL_ORDER,
    build_equivalence_catalog,
    contribution_signature,
    fit_equivalence_plan,
)


def _donor(hid: str, size: int, ages: list[int], sexes: list[int], weight: float = 1.0):
    row = {"H_ID": hid, "H_GR": size, "H_GEW": weight}
    for slot in range(1, 6):
        row[f"HP_ALTER_{slot}"] = ages[slot - 1] if slot <= size else 0
        row[f"HP_SEX_{slot}"] = sexes[slot - 1] if slot <= size else 1
    return row


def test_contribution_signature_has_household_mass():
    row = pd.Series(_donor("1", 2, [40, 12], [1, 2]))
    signature = contribution_signature(row)
    assert len(signature) == len(CELL_ORDER)
    assert sum(signature) == 2


def test_equivalence_catalog_collapses_same_fit_contribution():
    frame = pd.DataFrame(
        [
            _donor("1", 1, [40], [1], 2.0),
            _donor("2", 1, [41], [1], 3.0),
            _donor("3", 1, [41], [2], 4.0),
        ]
    )
    catalog = build_equivalence_catalog(frame)
    assert len(catalog) == 2
    male = catalog[catalog["donor_ids"].map(lambda ids: "1" in ids)].iloc[0]
    assert male["donor_count"] == 2
    assert male["donor_weight_sum"] == 5.0


def test_fit_equivalence_plan_exact_household_and_person_totals():
    donors = pd.DataFrame(
        [
            _donor("1", 1, [40], [1]),
            _donor("2", 1, [40], [2]),
        ]
    )
    catalog = build_equivalence_catalog(donors)
    age_codes = sorted({cell[0] for cell in CELL_ORDER})
    sex_codes = ["GESM", "GESW"]
    rows = []
    for age_code in age_codes:
        for sex_code in sex_codes:
            rows.append(
                {
                    "bezirk_code": "B1",
                    "bezirk_name": "B1",
                    "household_size_code": "PERSON01",
                    "age_zensus_11_source_code": age_code,
                    "sex_code": sex_code,
                    "projected_persons": 3
                    if age_code == "ALT040B049" and sex_code == "GESM"
                    else 2
                    if age_code == "ALT040B049" and sex_code == "GESW"
                    else 0,
                }
            )
    # Add zero-person groups for exact sizes 2..5; the fitter still has to see all five groups.
    for size in range(2, 6):
        for age_code in age_codes:
            for sex_code in sex_codes:
                rows.append(
                    {
                        "bezirk_code": "B1",
                        "bezirk_name": "B1",
                        "household_size_code": f"PERSON0{size}",
                        "age_zensus_11_source_code": age_code,
                        "sex_code": sex_code,
                        "projected_persons": 0,
                    }
                )
    # Add one donor class per sizes 2..5 so empty target groups are legal.
    extra = []
    for size in range(2, 6):
        extra.append(_donor(str(10 + size), size, [40] * size, [1] * size))
    catalog = build_equivalence_catalog(pd.concat([donors, pd.DataFrame(extra)], ignore_index=True))
    plan, fit, audit = fit_equivalence_plan(pd.DataFrame(rows), catalog)
    assert audit.target_households == 5
    assert audit.generated_households == 5
    assert audit.target_persons == 5
    assert audit.generated_persons == 5
    assert audit.l1_person_cell_error == 0
    assert plan["n_households"].sum() == 5
    assert fit["absolute_error"].sum() == 0


def test_fit_equivalence_plan_is_deterministic():
    donors = pd.DataFrame(
        [
            _donor("1", 1, [40], [1], 1.0),
            _donor("2", 1, [40], [2], 1.0),
        ]
    )
    extra = [_donor(str(10 + size), size, [40] * size, [1] * size) for size in range(2, 6)]
    catalog = build_equivalence_catalog(pd.concat([donors, pd.DataFrame(extra)], ignore_index=True))
    rows = []
    for size in range(1, 6):
        for age_code, sex_code in CELL_ORDER:
            value = 0
            if size == 1 and age_code == "ALT040B049":
                value = 3 if sex_code == "GESM" else 2
            rows.append(
                {
                    "bezirk_code": "B1",
                    "bezirk_name": "B1",
                    "household_size_code": f"PERSON0{size}",
                    "age_zensus_11_source_code": age_code,
                    "sex_code": sex_code,
                    "projected_persons": value,
                }
            )
    first = fit_equivalence_plan(pd.DataFrame(rows), catalog)[0]
    second = fit_equivalence_plan(pd.DataFrame(rows), catalog)[0]
    pd.testing.assert_frame_equal(first, second)
