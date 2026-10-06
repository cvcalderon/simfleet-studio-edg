from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from simfleet_edg.canonical.mobility import ActivityIntent, PersonDayPlan, TripDemand

DAY_REQUIRED = {
    "pipeline",
    "replicate_index",
    "row_id",
    "source_household_id",
    "source_person_id",
    "trip_day",
    "trip_count",
    "final_activity",
    "return_home",
    "temporal_chain_valid",
    "distance_chain_valid",
}

TRIP_REQUIRED = {
    "pipeline",
    "replicate_index",
    "row_id",
    "source_household_id",
    "source_person_id",
    "trip_index",
    "trip_count",
    "origin_activity",
    "destination_activity",
    "departure_clock_minute",
    "arrival_absolute_minute",
    "duration_from_clock_min",
    "distance_prior_km",
}

FORBIDDEN_COLUMNS = {
    "canonical_trip_purpose",
    "target_destination_activity",
    "source_trip_id",
    "fit_weight_W_GEW",
    "target_trip_day",
    "target_trip_count",
    "target_departure_clock_minute",
    "target_duration_from_clock_min",
    "target_distance_prior_km",
    "wegkm",
    "wegkm_imp",
    "chosen_mode",
    "selected_mode",
    "realized_route",
    "realised_route",
    "realized_travel_time",
    "realised_travel_time",
    "execution_outcome",
}


def _require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{label} missing required columns: {missing}")
    forbidden = sorted(FORBIDDEN_COLUMNS & set(frame.columns))
    if forbidden:
        raise ValueError(f"{label} contains forbidden future/target columns: {forbidden}")


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1"}:
        return True
    if text in {"false", "0"}:
        return False
    raise ValueError(f"Cannot coerce to bool: {value!r}")


def _build_activities(trips: tuple[TripDemand, ...]) -> tuple[ActivityIntent, ...]:
    if not trips:
        return ()

    activities: list[ActivityIntent] = [
        ActivityIntent(
            activity_index=0,
            activity=trips[0].origin_activity,
            arrival_absolute_minute=None,
            departure_clock_minute=trips[0].departure_clock_minute,
        )
    ]

    for index, trip in enumerate(trips, start=1):
        next_departure = trips[index].departure_clock_minute if index < len(trips) else None
        activities.append(
            ActivityIntent(
                activity_index=index,
                activity=trip.destination_activity,
                arrival_absolute_minute=trip.arrival_absolute_minute,
                departure_clock_minute=next_departure,
            )
        )

    return tuple(activities)


def adapt_joint_generated_frames(
    day_rows: pd.DataFrame,
    trip_rows: pd.DataFrame,
    *,
    pipeline: str = "SELECTED",
) -> tuple[PersonDayPlan, ...]:
    """Adapt frozen F3 joint-generator output rows into canonical M3 input.

    This function does not execute D_GEN and does not read CAL or TEST data.
    It only validates and transforms already-generated runtime-shaped rows.
    """
    _require_columns(day_rows, DAY_REQUIRED, "day_rows")
    _require_columns(trip_rows, TRIP_REQUIRED, "trip_rows")

    days = day_rows.loc[day_rows["pipeline"].astype(str).eq(pipeline)].copy()
    trips = trip_rows.loc[trip_rows["pipeline"].astype(str).eq(pipeline)].copy()

    if days.empty:
        raise ValueError(f"No day rows for pipeline={pipeline}")

    key_columns = ["replicate_index", "row_id"]
    if days.duplicated(key_columns).any():
        raise ValueError("day_rows contains duplicate replicate_index/row_id keys")

    trip_key_columns = ["replicate_index", "row_id", "trip_index"]
    if trips.duplicated(trip_key_columns).any():
        raise ValueError("trip_rows contains duplicate trip keys")

    plans: list[PersonDayPlan] = []

    for _, day in days.sort_values(key_columns, kind="stable").iterrows():
        replicate_index = int(day["replicate_index"])
        row_id = str(day["row_id"])
        household_id = str(day["source_household_id"])
        person_id = str(day["source_person_id"])

        mask = (
            trips["replicate_index"].astype(int).eq(replicate_index)
            & trips["row_id"].astype(str).eq(row_id)
        )
        subset = trips.loc[mask].sort_values("trip_index", kind="stable")

        declared_count = int(day["trip_count"])
        declared_trip_day = _as_bool(day["trip_day"])

        if len(subset) != declared_count:
            raise ValueError(
                f"Trip count mismatch for replicate={replicate_index}, row_id={row_id}: "
                f"{len(subset)} != {declared_count}"
            )

        if declared_trip_day != (declared_count > 0):
            raise ValueError(
                f"trip_day/trip_count mismatch for replicate={replicate_index}, row_id={row_id}"
            )

        trip_objects: list[TripDemand] = []

        expected_indexes = list(range(1, declared_count + 1))
        observed_indexes = subset["trip_index"].astype(int).tolist()
        if observed_indexes != expected_indexes:
            raise ValueError(
                f"Non-contiguous trip_index for replicate={replicate_index}, row_id={row_id}"
            )

        previous_destination: str | None = None
        previous_arrival: int | None = None

        for _, row in subset.iterrows():
            if str(row["source_household_id"]) != household_id:
                raise ValueError("Trip household identity differs from day identity")
            if str(row["source_person_id"]) != person_id:
                raise ValueError("Trip person identity differs from day identity")
            if int(row["trip_count"]) != declared_count:
                raise ValueError("Trip row trip_count differs from day trip_count")

            origin = str(row["origin_activity"])
            destination = str(row["destination_activity"])
            departure = int(row["departure_clock_minute"])
            arrival = int(row["arrival_absolute_minute"])

            if previous_destination is not None and origin != previous_destination:
                raise ValueError("Activity-chain discontinuity")
            if previous_arrival is not None and departure < previous_arrival:
                raise ValueError("Temporal-chain discontinuity")

            trip = TripDemand(
                trip_index=int(row["trip_index"]),
                origin_activity=origin,
                destination_activity=destination,
                departure_clock_minute=departure,
                arrival_absolute_minute=arrival,
                duration_from_clock_min=int(row["duration_from_clock_min"]),
                distance_prior_km=float(row["distance_prior_km"]),
            )
            trip_objects.append(trip)
            previous_destination = destination
            previous_arrival = arrival

        trip_tuple = tuple(trip_objects)
        activities = _build_activities(trip_tuple)

        if trip_tuple:
            if str(day["final_activity"]) != trip_tuple[-1].destination_activity:
                raise ValueError("final_activity does not match final trip destination")
            if _as_bool(day["return_home"]) != (
                trip_tuple[-1].destination_activity == "HOME"
            ):
                raise ValueError("return_home does not match final activity")
        elif str(day["final_activity"]) not in {"", "nan", "None"}:
            raise ValueError("Non-trip day must not declare a final activity")

        plans.append(
            PersonDayPlan(
                person_id=person_id,
                household_id=household_id,
                day_id=row_id,
                pipeline=pipeline,
                replicate_index=replicate_index,
                trip_day=declared_trip_day,
                trips=trip_tuple,
                activities=activities,
                return_home=_as_bool(day["return_home"]),
                temporal_chain_valid=_as_bool(day["temporal_chain_valid"]),
                distance_chain_valid=_as_bool(day["distance_chain_valid"]),
            )
        )

    return tuple(plans)


def flatten_trip_demands(plans: Iterable[PersonDayPlan]) -> tuple[TripDemand, ...]:
    return tuple(trip for plan in plans for trip in plan.trips)
