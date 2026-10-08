"""Production M1 -> D_GEN runtime context binding for F4.1d.

This module consumes only accepted M1 runtime tables and explicit scenario-known
context. It never reads MiD CAL/TEST evidence and never exposes donor identities
as behavioral predictors.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Final

import pandas as pd

from simfleet_edg.demand.training_data import _stock_class

RUNTIME_STATIC_COLUMNS: Final[tuple[str, ...]] = (
    "age_infr_class",
    "sex",
    "primary_activity_status",
    "household_size_class",
    "source_weekday",
    "source_season",
    "hh_car_stock_class",
    "hh_motorcycle_moped_stock_class",
    "hh_ebike_stock_class",
    "hh_bike_stock_class",
    "hh_carsharing_membership",
    "person_car_access",
    "person_bike_access",
    "person_ebike_access",
    "person_carsharing_membership",
)

PERSON_REQUIRED: Final[set[str]] = {
    "person_id",
    "household_id",
    "age_infr_class",
    "sex",
    "primary_activity_status",
    "person_enrichment_status",
}
HOUSEHOLD_REQUIRED: Final[set[str]] = {"household_id", "materialized_member_count"}
RESOURCE_REQUIRED: Final[set[str]] = {
    "household_id",
    "person_id",
    "resource_type",
    "scope",
    "relation_type",
    "quantity",
    "access_level",
    "membership_level",
}


@dataclass(frozen=True)
class ScenarioDayContext:
    scenario_id: str
    scenario_weekday: int
    scenario_season: int

    def __post_init__(self) -> None:
        if not str(self.scenario_id).strip():
            raise ValueError("scenario_id must be non-empty")
        if not 1 <= int(self.scenario_weekday) <= 7:
            raise ValueError("scenario_weekday must be in 1..7")
        if not 1 <= int(self.scenario_season) <= 4:
            raise ValueError("scenario_season must be in 1..4")


@dataclass(frozen=True)
class RuntimeContext:
    scenario: ScenarioDayContext
    frame: pd.DataFrame

    def select_first_persons(self, count: int) -> RuntimeContext:
        if count < 1:
            raise ValueError("count must be positive")
        ordered = self.frame.sort_values("source_person_id", kind="mergesort").head(count).copy()
        if len(ordered) != count:
            raise ValueError(f"Requested {count} persons but runtime context has {len(ordered)}")
        return RuntimeContext(self.scenario, ordered.reset_index(drop=True))


def runtime_row_id(scenario_id: str, person_id: str) -> str:
    payload = f"F4_1D|{scenario_id}|{person_id}".encode()
    return hashlib.sha256(payload).hexdigest()


def _require(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{label} missing required columns: {missing}")


def _one_row_per_key(frame: pd.DataFrame, keys: list[str], label: str) -> None:
    if frame.duplicated(keys).any():
        duplicated = frame.loc[frame.duplicated(keys, keep=False), keys].head(5).to_dict("records")
        raise ValueError(f"{label} contains duplicate keys {keys}: {duplicated}")


def _clean_category(value: Any) -> str:
    if pd.isna(value):
        return "UNKNOWN"
    text = str(value).strip()
    return text if text and text.lower() != "nan" else "UNKNOWN"


def _resource_subset(
    resources: pd.DataFrame,
    *,
    scope: str,
    relation_type: str,
    resource_type: str,
) -> pd.DataFrame:
    return resources.loc[
        resources["scope"].astype(str).eq(scope)
        & resources["relation_type"].astype(str).eq(relation_type)
        & resources["resource_type"].astype(str).eq(resource_type)
    ].copy()


def _household_resource_map(
    resources: pd.DataFrame,
    *,
    resource_type: str,
    relation_type: str,
    value_column: str,
) -> dict[str, Any]:
    subset = _resource_subset(
        resources,
        scope="HOUSEHOLD",
        relation_type=relation_type,
        resource_type=resource_type,
    )
    _one_row_per_key(subset, ["household_id"], f"household {resource_type}")
    return dict(zip(subset["household_id"].astype(str), subset[value_column], strict=True))


def _person_resource_map(
    resources: pd.DataFrame,
    *,
    resource_type: str,
    relation_type: str,
    value_column: str,
) -> dict[str, Any]:
    subset = _resource_subset(
        resources,
        scope="PERSON",
        relation_type=relation_type,
        resource_type=resource_type,
    )
    _one_row_per_key(subset, ["person_id"], f"person {resource_type}")
    if subset["person_id"].isna().any():
        raise ValueError(f"person {resource_type} contains null person_id")
    return dict(zip(subset["person_id"].astype(str), subset[value_column], strict=True))


def _map_required(series: pd.Series, mapping: dict[str, Any], label: str) -> pd.Series:
    keys = series.astype(str)
    missing = sorted(set(keys) - set(mapping))
    if missing:
        raise ValueError(f"Missing {label} resource rows for {len(missing)} identities: {missing[:5]}")
    return keys.map(mapping)


def _map_person_resource(
    person_ids: pd.Series,
    enrichment_status: pd.Series,
    mapping: dict[str, Any],
    label: str,
) -> pd.Series:
    keys = person_ids.astype(str)
    statuses = enrichment_status.astype(str)
    allowed_statuses = {"LINKED_PERSONEN", "ROSTER_ONLY_NO_PERSONEN"}
    unexpected_statuses = sorted(set(statuses) - allowed_statuses)
    if unexpected_statuses:
        raise ValueError(f"Unexpected person_enrichment_status values: {unexpected_statuses}")

    linked = statuses.eq("LINKED_PERSONEN")
    roster_only = statuses.eq("ROSTER_ONLY_NO_PERSONEN")
    missing_linked = sorted(set(keys[linked]) - set(mapping))
    if missing_linked:
        raise ValueError(
            f"Missing {label} resource rows for {len(missing_linked)} linked identities: "
            f"{missing_linked[:5]}"
        )

    fabricated_roster_rows = sorted(set(keys[roster_only]) & set(mapping))
    if fabricated_roster_rows:
        raise ValueError(
            f"Roster-only identities unexpectedly have {label} resource rows: "
            f"{fabricated_roster_rows[:5]}"
        )

    values = keys.map(mapping)
    values.loc[roster_only] = "UNKNOWN"
    return values


def build_runtime_context(
    households: pd.DataFrame,
    persons: pd.DataFrame,
    resources: pd.DataFrame,
    scenario: ScenarioDayContext,
) -> RuntimeContext:
    """Build one deterministic runtime row per accepted M1 person."""
    _require(households, HOUSEHOLD_REQUIRED, "households")
    _require(persons, PERSON_REQUIRED, "persons")
    _require(resources, RESOURCE_REQUIRED, "resources")

    if households["household_id"].duplicated().any():
        raise ValueError("households household_id must be unique")
    if persons["person_id"].duplicated().any():
        raise ValueError("persons person_id must be unique")

    household_ids = set(households["household_id"].astype(str))
    if not persons["household_id"].astype(str).isin(household_ids).all():
        raise ValueError("persons contains household_id outside accepted households")

    member_counts = persons.assign(_hh=persons["household_id"].astype(str)).groupby("_hh").size()
    declared = households.set_index(households["household_id"].astype(str))[
        "materialized_member_count"
    ].astype(int)
    observed = member_counts.reindex(declared.index, fill_value=0).astype(int)
    if not observed.equals(declared):
        raise ValueError("M1 materialized_member_count differs from accepted person membership")
    if (declared < 1).any():
        raise ValueError("household member count must be positive")

    hh_size = {key: (str(value) if value <= 5 else "6_PLUS") for key, value in declared.items()}

    hh_car = _household_resource_map(
        resources, resource_type="CAR", relation_type="HOUSEHOLD_STOCK", value_column="quantity"
    )
    hh_moto = _household_resource_map(
        resources,
        resource_type="MOTORCYCLE_MOPED",
        relation_type="HOUSEHOLD_STOCK",
        value_column="quantity",
    )
    hh_ebike = _household_resource_map(
        resources, resource_type="EBIKE", relation_type="HOUSEHOLD_STOCK", value_column="quantity"
    )
    hh_bike = _household_resource_map(
        resources, resource_type="BIKE", relation_type="HOUSEHOLD_STOCK", value_column="quantity"
    )
    hh_cs = _household_resource_map(
        resources,
        resource_type="CARSHARING",
        relation_type="MEMBERSHIP",
        value_column="membership_level",
    )
    p_car = _person_resource_map(
        resources, resource_type="CAR", relation_type="PERSON_ACCESS", value_column="access_level"
    )
    p_bike = _person_resource_map(
        resources, resource_type="BIKE", relation_type="PERSON_ACCESS", value_column="access_level"
    )
    p_ebike = _person_resource_map(
        resources, resource_type="EBIKE", relation_type="PERSON_ACCESS", value_column="access_level"
    )
    p_cs = _person_resource_map(
        resources,
        resource_type="CARSHARING",
        relation_type="MEMBERSHIP",
        value_column="membership_level",
    )

    frame = persons[[
        "person_id",
        "household_id",
        "age_infr_class",
        "sex",
        "primary_activity_status",
        "person_enrichment_status",
    ]].copy()
    frame["person_id"] = frame["person_id"].astype(str)
    frame["household_id"] = frame["household_id"].astype(str)
    frame = frame.rename(
        columns={"person_id": "source_person_id", "household_id": "source_household_id"}
    )

    frame.insert(
        0,
        "row_id",
        [runtime_row_id(scenario.scenario_id, person_id) for person_id in frame["source_person_id"]],
    )
    frame["household_size_class"] = frame["source_household_id"].map(hh_size)
    frame["source_weekday"] = int(scenario.scenario_weekday)
    frame["source_season"] = int(scenario.scenario_season)
    frame["hh_car_stock_class"] = _map_required(
        frame["source_household_id"], hh_car, "household CAR"
    ).map(lambda value: _stock_class(value, 3))
    frame["hh_motorcycle_moped_stock_class"] = _map_required(
        frame["source_household_id"], hh_moto, "household MOTORCYCLE_MOPED"
    ).map(lambda value: _stock_class(value, 3))
    frame["hh_ebike_stock_class"] = _map_required(
        frame["source_household_id"], hh_ebike, "household EBIKE"
    ).map(lambda value: _stock_class(value, 10))
    frame["hh_bike_stock_class"] = _map_required(
        frame["source_household_id"], hh_bike, "household BIKE"
    ).map(lambda value: _stock_class(value, 10))
    frame["hh_carsharing_membership"] = _map_required(
        frame["source_household_id"], hh_cs, "household CARSHARING"
    ).map(_clean_category)
    frame["person_car_access"] = _map_person_resource(
        frame["source_person_id"],
        frame["person_enrichment_status"],
        p_car,
        "person CAR",
    ).map(_clean_category)
    frame["person_bike_access"] = _map_person_resource(
        frame["source_person_id"],
        frame["person_enrichment_status"],
        p_bike,
        "person BIKE",
    ).map(_clean_category)
    frame["person_ebike_access"] = _map_person_resource(
        frame["source_person_id"],
        frame["person_enrichment_status"],
        p_ebike,
        "person EBIKE",
    ).map(_clean_category)
    frame["person_carsharing_membership"] = _map_person_resource(
        frame["source_person_id"],
        frame["person_enrichment_status"],
        p_cs,
        "person CARSHARING",
    ).map(_clean_category)

    # Normalize direct categorical person fields without consulting donor provenance.
    for column in ("age_infr_class", "sex", "primary_activity_status"):
        frame[column] = frame[column].map(_clean_category)

    ordered = ["row_id", "source_household_id", "source_person_id", *RUNTIME_STATIC_COLUMNS]
    frame = frame[ordered].sort_values("source_person_id", kind="mergesort").reset_index(drop=True)
    if frame["row_id"].duplicated().any():
        raise ValueError("runtime row_id collision")
    return RuntimeContext(scenario=scenario, frame=frame)
