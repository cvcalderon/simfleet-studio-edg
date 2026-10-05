from __future__ import annotations

import pandas as pd

from simfleet_edg.population.candidate_materialization import (
    TrainCatalog,
    build_pconstr_selection,
    build_ptrs_selection,
)
from simfleet_edg.population.equivalence import build_equivalence_catalog, donor_to_equivalence_map


def _strict_frame() -> pd.DataFrame:
    rows = []
    for hid, size, weight, sex in [("1", 1, 1.0, 1), ("2", 1, 9.0, 1), ("3", 2, 1.0, 2), ("4", 3, 1.0, 1), ("5", 4, 1.0, 2), ("6", 5, 1.0, 1)]:
        row = {"H_ID": hid, "H_GR": size, "H_GEW": weight, "H_HOCH": 1.0}
        for slot in range(1, 6):
            row[f"HP_ALTER_{slot}"] = 40
            row[f"HP_SEX_{slot}"] = sex
        rows.append(row)
    return pd.DataFrame(rows)


def _catalog() -> TrainCatalog:
    strict = _strict_frame()
    eq = build_equivalence_catalog(strict)
    return TrainCatalog(
        strict_households=strict,
        six_plus_households=pd.DataFrame(),
        private_persons=pd.DataFrame(),
        person_lookup={},
        equivalence_catalog=eq,
        donor_to_class=donor_to_equivalence_map(eq),
        split_by_household={str(i): "TRAIN" for i in range(1, 7)},
    )


def test_pconstr_selection_preserves_fitted_class_counts():
    catalog = _catalog()
    class_id = catalog.donor_to_class["1"]
    plan = pd.DataFrame(
        [
            {
                "bezirk_code": "B1",
                "bezirk_name": "B1",
                "household_size": 1,
                "household_size_code": "PERSON01",
                "equivalence_class_id": class_id,
                "n_households": 20,
            }
        ]
    )
    selected = build_pconstr_selection(
        plan, catalog, scale_id="S", variant_id="P_CONSTR_RMIN_V2_HD_U"
    )
    assert len(selected) == 20
    assert set(selected["source_household_id"]) <= {"1", "2"}
    assert selected["equivalence_class_id"].nunique() == 1


def test_uniform_and_weighted_are_distinct_but_deterministic():
    catalog = _catalog()
    class_id = catalog.donor_to_class["1"]
    plan = pd.DataFrame(
        [
            {
                "bezirk_code": "B1",
                "bezirk_name": "B1",
                "household_size": 1,
                "household_size_code": "PERSON01",
                "equivalence_class_id": class_id,
                "n_households": 100,
            }
        ]
    )
    uniform = build_pconstr_selection(
        plan, catalog, scale_id="S", variant_id="P_CONSTR_RMIN_V2_HD_U"
    )
    weighted = build_pconstr_selection(
        plan, catalog, scale_id="S", variant_id="P_CONSTR_RMIN_V2_HD_W"
    )
    weighted2 = build_pconstr_selection(
        plan, catalog, scale_id="S", variant_id="P_CONSTR_RMIN_V2_HD_W"
    )
    pd.testing.assert_frame_equal(weighted, weighted2)
    assert uniform["source_household_id"].tolist() != weighted["source_household_id"].tolist()
    assert (weighted["source_household_id"] == "2").sum() > (uniform["source_household_id"] == "2").sum()


def test_ptrs_exact_person_target_without_composition_fit():
    catalog = _catalog()
    rows = []
    for age_code in ["ALT040B049"]:
        for sex_code in ["GESM", "GESW"]:
            for size_code, value in [("PERSON01", 3), ("PERSON02", 4), ("PERSON06UM", 0)]:
                rows.append(
                    {
                        "bezirk_code": "B1",
                        "bezirk_name": "B1",
                        "age_zensus_11_source_code": age_code,
                        "sex_code": sex_code,
                        "household_size_code": size_code,
                        "projected_persons": value if sex_code == "GESM" else 0,
                    }
                )
    selected = build_ptrs_selection(pd.DataFrame(rows), catalog, scale_id="S")
    assert selected["household_size"].sum() == 7
    assert set(selected["source_household_id"]) <= {str(i) for i in range(1, 7)}
