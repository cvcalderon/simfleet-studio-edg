from __future__ import annotations

import pandas as pd
import pytest

from simfleet_edg.demand.runtime_context import (
    ScenarioDayContext,
    build_runtime_context,
    runtime_row_id,
)


def _tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    households = pd.DataFrame(
        [
            {"household_id": "HH_A", "materialized_member_count": 6},
            {"household_id": "HH_B", "materialized_member_count": 1},
        ]
    )
    persons = pd.DataFrame(
        [
            {
                "person_id": f"P_A_{index}",
                "household_id": "HH_A",
                "age_infr_class": "ADULT",
                "sex": "MALE" if index % 2 else "FEMALE",
                "primary_activity_status": "EMPLOYED",
                "person_enrichment_status": "LINKED_PERSONEN",
            }
            for index in range(1, 7)
        ]
        + [
            {
                "person_id": "P_B_1",
                "household_id": "HH_B",
                "age_infr_class": "ADULT",
                "sex": "FEMALE",
                "primary_activity_status": "STUDENT",
                "person_enrichment_status": "LINKED_PERSONEN",
            }
        ]
    )
    rows: list[dict[str, object]] = []
    for household_id in ("HH_A", "HH_B"):
        quantities = {"CAR": 4.0, "MOTORCYCLE_MOPED": 1.0, "EBIKE": 2.0, "BIKE": 12.0}
        for resource_type, quantity in quantities.items():
            rows.append(
                {
                    "household_id": household_id,
                    "person_id": None,
                    "resource_type": resource_type,
                    "scope": "HOUSEHOLD",
                    "relation_type": "HOUSEHOLD_STOCK",
                    "quantity": quantity,
                    "access_level": None,
                    "membership_level": None,
                }
            )
        rows.append(
            {
                "household_id": household_id,
                "person_id": None,
                "resource_type": "CARSHARING",
                "scope": "HOUSEHOLD",
                "relation_type": "MEMBERSHIP",
                "quantity": None,
                "access_level": None,
                "membership_level": "NONE",
            }
        )
    for person_id, household_id in persons[["person_id", "household_id"]].itertuples(index=False):
        for resource_type, access in (("CAR", "ALWAYS"), ("BIKE", "YES"), ("EBIKE", "NO")):
            rows.append(
                {
                    "household_id": household_id,
                    "person_id": person_id,
                    "resource_type": resource_type,
                    "scope": "PERSON",
                    "relation_type": "PERSON_ACCESS",
                    "quantity": None,
                    "access_level": access,
                    "membership_level": None,
                }
            )
        rows.append(
            {
                "household_id": household_id,
                "person_id": person_id,
                "resource_type": "CARSHARING",
                "scope": "PERSON",
                "relation_type": "MEMBERSHIP",
                "quantity": None,
                "access_level": None,
                "membership_level": "ONE_PROVIDER",
            }
        )
    return households, persons, pd.DataFrame(rows)


def test_runtime_context_preserves_six_plus_and_scenario_aliases() -> None:
    households, persons, resources = _tables()
    scenario = ScenarioDayContext("SCENARIO_X", 3, 2)
    runtime = build_runtime_context(households, persons, resources, scenario)
    frame = runtime.frame.set_index("source_person_id")

    assert set(frame.loc[[f"P_A_{i}" for i in range(1, 7)], "household_size_class"]) == {"6_PLUS"}
    assert frame.loc["P_B_1", "household_size_class"] == "1"
    assert set(frame["source_weekday"]) == {3}
    assert set(frame["source_season"]) == {2}
    assert set(frame["hh_car_stock_class"]) == {"3_PLUS"}
    assert set(frame["hh_bike_stock_class"]) == {"10_PLUS"}
    assert frame.loc["P_A_1", "row_id"] == runtime_row_id("SCENARIO_X", "P_A_1")


def test_runtime_context_uses_generated_ids_not_donor_ids() -> None:
    households, persons, resources = _tables()
    persons["source_person_id"] = "DONOR_FORBIDDEN"
    households["source_household_id"] = "DONOR_HH_FORBIDDEN"
    runtime = build_runtime_context(
        households, persons, resources, ScenarioDayContext("SCENARIO_X", 1, 1)
    )
    assert set(runtime.frame["source_person_id"]) == set(persons["person_id"])
    assert "DONOR_FORBIDDEN" not in set(runtime.frame["source_person_id"])


def test_runtime_context_rejects_missing_person_resource() -> None:
    households, persons, resources = _tables()
    resources = resources.loc[
        ~(
            resources["person_id"].eq("P_B_1")
            & resources["resource_type"].eq("CAR")
            & resources["relation_type"].eq("PERSON_ACCESS")
        )
    ]
    with pytest.raises(ValueError, match="Missing person CAR resource rows"):
        build_runtime_context(
            households, persons, resources, ScenarioDayContext("SCENARIO_X", 1, 1)
        )


def test_runtime_context_maps_roster_only_person_resources_to_unknown() -> None:
    households, persons, resources = _tables()
    persons.loc[persons["person_id"].eq("P_B_1"), "person_enrichment_status"] = (
        "ROSTER_ONLY_NO_PERSONEN"
    )
    resources = resources.loc[~resources["person_id"].eq("P_B_1")].copy()

    runtime = build_runtime_context(
        households, persons, resources, ScenarioDayContext("SCENARIO_X", 1, 1)
    )
    row = runtime.frame.set_index("source_person_id").loc["P_B_1"]

    assert row["person_car_access"] == "UNKNOWN"
    assert row["person_bike_access"] == "UNKNOWN"
    assert row["person_ebike_access"] == "UNKNOWN"
    assert row["person_carsharing_membership"] == "UNKNOWN"


def test_scenario_context_bounds() -> None:
    with pytest.raises(ValueError):
        ScenarioDayContext("", 1, 1)
    with pytest.raises(ValueError):
        ScenarioDayContext("X", 0, 1)
    with pytest.raises(ValueError):
        ScenarioDayContext("X", 1, 5)
