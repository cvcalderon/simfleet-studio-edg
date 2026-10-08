"""Frozen selected D_GEN production runtime generator for F4.1d."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

from simfleet_edg.demand.participation import transform_context
from simfleet_edg.demand.runtime_context import RuntimeContext
from simfleet_edg.demand.time_schedule import transform_time_b_context, validate_temporal_row
from simfleet_edg.evaluation.activity_chain_adapter import ActivityChainAdapter
from simfleet_edg.evaluation.cal_adapter_common import (
    ArtifactRecord,
    canonical_category,
    load_registry,
)
from simfleet_edg.evaluation.cal_protocol import runtime_draw_seed
from simfleet_edg.evaluation.cal_state import (
    propagated_chain_state,
    propagated_distance_state,
    propagated_time_state,
)
from simfleet_edg.evaluation.distance_prior_adapter import DistancePriorAdapter
from simfleet_edg.evaluation.participation_adapter import ParticipationAdapter
from simfleet_edg.evaluation.time_schedule_adapter import TimeScheduleAdapter
from simfleet_edg.evaluation.trip_count_adapter import TripCountAdapter

MASTER_SEED: Final[int] = 20261007
PIPELINE_LABEL: Final[str] = "SELECTED"

SELECTED_ARTIFACTS: Final[tuple[tuple[str, str, str], ...]] = (
    (
        "DG_PARTICIPATION::PART_A::PA1",
        "18f59f65dc2fe6afa2934b36d8d3989d6ff278fd7d940af08f8954075305782e",
        "00b12204a690070eed5eca9c399c821cf5b6a5912e6fcd2423dab41e22395989",
    ),
    (
        "DG_TRIP_COUNT::COUNT_REF::REFERENCE",
        "647e38736a9e67b81064c5ef52d1644d58c7954984336bc74eeb06e9bfb905e8",
        "5cafa1ff9193f8e3e4343d1ba995ea5e09bb3712988896b53a0c0ae1b22b8669",
    ),
    (
        "DG_ACTIVITY_CHAIN::CHAIN_A::CHA2",
        "242085ebab9eb5ec8a53ea3b8ffe65c1d1e1fdb660bcacff0ab172d1b5ef1ecf",
        "337140dd45522a47659603998838a3c869646cbd70961ba874d6f34be555ea73",
    ),
    (
        "TIME_B_TB2",
        "74aa012647291854c4fa087f1dd798e9d909e3c681046f1447307a23a6d5f900",
        "ff3caa54e7ee11c2bde79e49da5604277d506c826b891fb7a1e4edd04b157c5a",
    ),
    (
        "DIST_REF_REFERENCE",
        "21554c37d44aad7144c8daac1ddfd9e9a63402d59e105f9e790e83c1ea6e4cab",
        "4a30ae1f586418c31a55028e2902d28c43e234a1fddaadccba9103c1a09bd409",
    ),
)


@dataclass(frozen=True)
class SelectedAdapters:
    participation: ParticipationAdapter
    trip_count: TripCountAdapter
    chain: ActivityChainAdapter
    time: TimeScheduleAdapter
    distance: DistancePriorAdapter


@dataclass(frozen=True)
class GenerationResult:
    day_rows: pd.DataFrame
    trip_rows: pd.DataFrame
    support_audit: dict[str, Any]
    artifact_validation: tuple[dict[str, Any], ...]
    projection_audit: pd.DataFrame


def _adapter(repo_root: Path, record: ArtifactRecord) -> Any:
    if record.component == "DG_PARTICIPATION":
        return ParticipationAdapter(repo_root, record)
    if record.component == "DG_TRIP_COUNT":
        return TripCountAdapter(repo_root, record)
    if record.component == "DG_ACTIVITY_CHAIN":
        return ActivityChainAdapter(repo_root, record)
    if record.component == "DG_TIME_SCHEDULE":
        return TimeScheduleAdapter(repo_root, record)
    if record.component == "DG_DISTANCE_PRIOR":
        return DistancePriorAdapter(repo_root, record)
    raise ValueError(f"Unsupported component: {record.component}")


def load_selected_adapters(repo_root: Path) -> tuple[SelectedAdapters, tuple[dict[str, Any], ...]]:
    registry_path = repo_root / "docs/F3_3_CANDIDATE_ARTIFACT_REGISTRY_v1.csv"
    records = load_registry(registry_path)
    index = {record.artifact_id: record for record in records}
    resolved: dict[str, Any] = {}
    validation: list[dict[str, Any]] = []

    for artifact_id, expected_model, expected_manifest in SELECTED_ARTIFACTS:
        record = index.get(artifact_id)
        if record is None:
            raise ValueError(f"Selected artifact absent from frozen registry: {artifact_id}")
        if record.model_sha256 != expected_model:
            raise ValueError(f"Model SHA mismatch in frozen registry: {artifact_id}")
        if record.manifest_sha256 != expected_manifest:
            raise ValueError(f"Manifest SHA mismatch in frozen registry: {artifact_id}")
        run_dir = record.validate(repo_root)
        resolved[record.component] = _adapter(repo_root, record)
        validation.append(
            {
                "component": record.component,
                "artifact_id": artifact_id,
                "model_sha256": expected_model,
                "manifest_sha256": expected_manifest,
                "run_dir": str(run_dir),
                "status": "PASS",
            }
        )

    expected_components = {
        "DG_PARTICIPATION",
        "DG_TRIP_COUNT",
        "DG_ACTIVITY_CHAIN",
        "DG_TIME_SCHEDULE",
        "DG_DISTANCE_PRIOR",
    }
    if set(resolved) != expected_components:
        raise ValueError("Selected pipeline did not resolve exactly five frozen components")
    return (
        SelectedAdapters(
            participation=resolved["DG_PARTICIPATION"],
            trip_count=resolved["DG_TRIP_COUNT"],
            chain=resolved["DG_ACTIVITY_CHAIN"],
            time=resolved["DG_TIME_SCHEDULE"],
            distance=resolved["DG_DISTANCE_PRIOR"],
        ),
        tuple(validation),
    )


def _one_row(state: dict[str, Any], required: list[str]) -> pd.DataFrame:
    missing = [column for column in required if column not in state]
    if missing:
        raise KeyError(f"Runtime state missing fields: {missing}")
    return pd.DataFrame([{column: state[column] for column in required}])


def _chain_selected_level(adapter: ActivityChainAdapter, state: dict[str, Any]) -> int:
    if adapter.record.candidate_id != "CHAIN_A":
        return 0
    for level_index, level in enumerate(adapter.model["levels"]):
        dims = list(level["dimensions"])
        requested = ("GLOBAL",) if dims == ["GLOBAL"] else tuple(
            canonical_category(state[column]) for column in dims
        )
        for cell in level["cells"]:
            key = tuple(str(item["value"]) for item in cell["key"])
            if key == requested and bool(cell["eligible_direct"]):
                return level_index
    raise RuntimeError("CHAIN_A deterministic backoff failed")


def _time_b_full_chain_sample(
    adapter: TimeScheduleAdapter,
    state: dict[str, Any],
    *,
    previous_arrival: int | None,
    trips_remaining: int,
    seed: int,
) -> tuple[dict[str, Any], dict[str, int]]:
    if adapter.record.candidate_id != "TIME_B" or adapter.encoder is None:
        raise ValueError("F4.1d selected time adapter must be TIME_B")
    required = list(adapter.encoder["categorical_columns"]) + list(adapter.encoder["numeric_columns"])
    frame = _one_row(state, required)
    _, unseen = transform_time_b_context(frame, adapter.encoder)
    repaired = adapter._time_b_quantiles(frame)
    dep_knots = repaired["departure_clock_minute"][0]
    dur_knots = repaired["duration_from_clock_min"][0]

    # This is the frozen propagated TIME_B minimum-slack conditional law used by
    # the selected joint pipeline. It is reproduced here without CAL data access.
    xp = np.asarray([0.0, *adapter.quantiles, 1.0], dtype=float)
    dep_fp = np.asarray([adapter.DEP_MIN, *dep_knots.tolist(), adapter.DEP_MAX], dtype=float)
    dur_fp = np.asarray([adapter.DUR_MIN, *dur_knots.tolist(), adapter.DUR_MAX], dtype=float)
    if np.any(np.diff(dep_fp) < -1e-12) or np.any(np.diff(dur_fp) < -1e-12):
        raise ValueError("TIME_B reconstruction knots are not monotone")

    def rounded_interp_pmf(fp: np.ndarray, lo: int, hi: int) -> tuple[np.ndarray, np.ndarray]:
        if np.any(np.diff(xp) <= 0) or np.any(np.diff(fp) < -1e-12):
            raise ValueError("Interpolation support must be ordered and monotone")

        def cdf_le(value: int) -> float:
            if value < lo:
                return 0.0
            if value >= hi:
                return 1.0
            threshold = float(value) + 0.5
            if fp[0] >= threshold:
                return 0.0
            for index in range(len(fp) - 1):
                y0 = float(fp[index])
                y1 = float(fp[index + 1])
                if y0 >= threshold:
                    return float(xp[index])
                if y1 >= threshold:
                    if y1 <= y0 + 1e-15:
                        return float(xp[index])
                    fraction = (threshold - y0) / (y1 - y0)
                    return float(xp[index] + fraction * (xp[index + 1] - xp[index]))
            return 1.0

        values = np.arange(lo, hi + 1, dtype=np.int32)
        cdf = np.asarray([cdf_le(int(value)) for value in values], dtype=float)
        previous = np.concatenate(([0.0], cdf[:-1]))
        probability = np.maximum(cdf - previous, 0.0)
        keep = probability > 1e-15
        values = values[keep]
        probability = probability[keep]
        total = float(probability.sum())
        if not np.isfinite(total) or total <= 0:
            raise RuntimeError("TIME_B reconstructed distribution has no probability mass")
        probability /= total
        return values, probability

    dep_values, dep_probability = rounded_interp_pmf(dep_fp, adapter.DEP_MIN, adapter.DEP_MAX)
    dur_values, dur_probability = rounded_interp_pmf(dur_fp, adapter.DUR_MIN, adapter.DUR_MAX)

    dep_feasible = np.ones(len(dep_values), dtype=bool)
    if previous_arrival is not None:
        dep_feasible &= dep_values >= int(previous_arrival)

    if trips_remaining > 0:
        arrival_limit = 1440 - trips_remaining
        dur_cdf = np.cumsum(dur_probability)
        max_duration = (arrival_limit - dep_values).astype(int)
        allowed_mass = np.zeros(len(dep_values), dtype=float)
        indices = np.searchsorted(dur_values, max_duration, side="right") - 1
        valid = indices >= 0
        allowed_mass[valid] = dur_cdf[indices[valid]]
    else:
        arrival_limit = adapter.DEP_MAX + adapter.DUR_MAX
        allowed_mass = np.ones(len(dep_values), dtype=float)

    dep_weight = dep_probability * dep_feasible.astype(float) * allowed_mass
    total = float(dep_weight.sum())
    if not np.isfinite(total) or total <= 0:
        raise RuntimeError("TIME_B has no full-chain minimum-slack support")
    dep_weight /= total

    rng = np.random.default_rng(seed)
    dep_index = int(rng.choice(len(dep_values), p=dep_weight))
    departure = int(dep_values[dep_index])
    dur_mask = dur_values <= arrival_limit - departure if trips_remaining > 0 else np.ones(
        len(dur_values), dtype=bool
    )
    feasible_dur_values = dur_values[dur_mask]
    feasible_dur_probability = dur_probability[dur_mask]
    duration_total = float(feasible_dur_probability.sum())
    if not np.isfinite(duration_total) or duration_total <= 0:
        raise RuntimeError("TIME_B has no feasible duration support after departure draw")
    feasible_dur_probability /= duration_total
    duration = int(rng.choice(feasible_dur_values, p=feasible_dur_probability))
    ok, result = validate_temporal_row(
        departure,
        duration,
        previous_arrival_absolute_minute=previous_arrival,
        trips_remaining_after_current=trips_remaining,
    )
    if not ok:
        raise RuntimeError("TIME_B full-chain sampler produced invalid temporal row")
    return result, {str(key): int(value) for key, value in unseen.items()}



# The M2 labels below are never changed inside CHA2/TIME/DIST calls. Projection
# takes place only after the entire selected five-component draw has completed.
M3_ACTIVITY_VOCABULARY: Final[frozenset[str]] = frozenset(
    {"HOME", "WORK", "BUSINESS", "EDUCATION", "ESCORT", "LEISURE", "OTHER", "SHOPPING"}
)
M2_M3_EXPLICIT_PROJECTION: Final[dict[str, str]] = {"PRIVATE_ERRAND": "OTHER"}
PROJECTION_AUDIT_COLUMNS: Final[tuple[str, ...]] = (
    "record_type", "row_id", "trip_index",
    "raw_origin_activity", "projected_origin_activity",
    "raw_destination_activity", "projected_destination_activity",
    "raw_final_activity", "projected_final_activity",
)


def _project_m2_label(raw: Any) -> str:
    if not isinstance(raw, str):
        raise ValueError(f"Invalid M2 activity type at M3 boundary: {type(raw).__name__}")
    if raw in M3_ACTIVITY_VOCABULARY:
        return raw
    if raw in M2_M3_EXPLICIT_PROJECTION:
        return M2_M3_EXPLICIT_PROJECTION[raw]
    raise ValueError(f"Unmapped M2 activity at M3 boundary: {raw!r}")


def project_m2_activity_frames(
    day_rows: pd.DataFrame, trip_rows: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, int]]:
    """Explicitly lossy M2->M3 projection, with complete deterministic raw provenance."""
    days = day_rows.copy(deep=True)
    trips = trip_rows.copy(deep=True)
    if days["row_id"].duplicated().any() or trips.duplicated(["row_id", "trip_index"]).any():
        raise ValueError("Duplicate M1 row/trip identity at taxonomy boundary")
    if not days["row_id"].is_unique or not set(trips["row_id"]).issubset(set(days["row_id"])):
        raise ValueError("Trip/day row_id relation is invalid")
    raw_trips = trips.sort_values(["row_id", "trip_index"], kind="mergesort")
    raw_days = days.sort_values("row_id", kind="mergesort")
    audit_rows: list[dict[str, Any]] = []
    origin_changes = 0
    destination_changes = 0
    final_changes = 0
    affected: set[str] = set()
    affected_trips: set[tuple[str, int]] = set()
    for idx, trip in raw_trips.iterrows():
        row_id = str(trip["row_id"])
        ti = int(trip["trip_index"])
        raw_o = trip["origin_activity"]
        raw_d = trip["destination_activity"]
        projected_o = _project_m2_label(raw_o)
        projected_d = _project_m2_label(raw_d)
        origin_changes += int(raw_o != projected_o)
        destination_changes += int(raw_d != projected_d)
        if raw_o != projected_o or raw_d != projected_d:
            affected.add(row_id)
            affected_trips.add((row_id, ti))
        trips.at[idx, "origin_activity"] = projected_o
        trips.at[idx, "destination_activity"] = projected_d
        audit_rows.append({
            "record_type": "TRIP", "row_id": row_id, "trip_index": ti,
            "raw_origin_activity": raw_o, "projected_origin_activity": projected_o,
            "raw_destination_activity": raw_d, "projected_destination_activity": projected_d,
            "raw_final_activity": "", "projected_final_activity": "",
        })
    for idx, day in raw_days.iterrows():
        row_id = str(day["row_id"])
        trip_count = int(day["trip_count"])
        day_trips = raw_trips.loc[raw_trips["row_id"].astype(str).eq(row_id)]
        if len(day_trips) != trip_count or sorted(day_trips["trip_index"].astype(int)) != list(range(1, trip_count + 1)):
            raise ValueError(f"Trip continuity/cardinality mismatch: {row_id}")
        raw_final = day["final_activity"]
        if trip_count == 0:
            if raw_final != "":
                raise ValueError(f"Nonempty final activity with zero trips: {row_id}")
            projected_final = ""
        else:
            raw_origin_chain = day_trips["origin_activity"].tolist()
            raw_destination_chain = day_trips["destination_activity"].tolist()
            if raw_origin_chain[1:] != raw_destination_chain[:-1]:
                raise ValueError(f"M2 chain discontinuity: {row_id}")
            if raw_final != raw_destination_chain[-1]:
                raise ValueError(f"M2 final activity mismatch: {row_id}")
            projected_final = _project_m2_label(raw_final)
            projected_trips = trips.loc[trips["row_id"].astype(str).eq(row_id)].sort_values("trip_index", kind="mergesort")
            projected_origins = projected_trips["origin_activity"].tolist()
            projected_destinations = projected_trips["destination_activity"].tolist()
            if projected_origins[1:] != projected_destinations[:-1] or projected_final != projected_destinations[-1]:
                raise ValueError(f"M3 chain discontinuity: {row_id}")
        final_changes += int(raw_final != projected_final)
        if raw_final != projected_final:
            affected.add(row_id)
        days.at[idx, "final_activity"] = projected_final
        audit_rows.append({
            "record_type": "DAY", "row_id": row_id, "trip_index": "",
            "raw_origin_activity": "", "projected_origin_activity": "",
            "raw_destination_activity": "", "projected_destination_activity": "",
            "raw_final_activity": raw_final, "projected_final_activity": projected_final,
        })
    audit = pd.DataFrame(audit_rows, columns=PROJECTION_AUDIT_COLUMNS)
    audit = audit.sort_values(["row_id", "record_type", "trip_index"], kind="mergesort").reset_index(drop=True)
    metrics = {
        "raw_private_errand_origin_rows": origin_changes,
        "raw_private_errand_destination_rows": destination_changes,
        "raw_private_errand_final_activity_days": final_changes,
        "affected_person_days": len(affected),
        "affected_trip_rows": len(affected_trips),
        "audit_day_rows": len(days),
        "audit_trip_rows": len(trips),
    }
    return days, trips, audit, metrics

class ProductionDGenGenerator:
    def __init__(
        self,
        repo_root: Path,
        *,
        adapters: SelectedAdapters | None = None,
        artifact_validation: tuple[dict[str, Any], ...] | None = None,
    ) -> None:
        self.repo_root = repo_root
        if adapters is None:
            loaded, validation = load_selected_adapters(repo_root)
            self.adapters = loaded
            self.artifact_validation = validation
        else:
            self.adapters = adapters
            self.artifact_validation = artifact_validation or ()

    def generate(self, runtime: RuntimeContext) -> GenerationResult:
        context = runtime.frame.sort_values("source_person_id", kind="mergesort").reset_index(drop=True)
        if context["source_person_id"].duplicated().any():
            raise ValueError("Runtime context contains duplicate accepted person ids")

        part_required = list(self.adapters.participation.required_columns)
        missing = [column for column in part_required if column not in context.columns]
        if missing:
            raise KeyError(f"Participation runtime context missing columns: {missing}")
        _, participation_unseen = transform_context(context[part_required], self.adapters.participation.encoder)

        unseen: dict[str, Counter[str]] = {
            component: Counter()
            for component in (
                "DG_PARTICIPATION",
                "DG_TRIP_COUNT",
                "DG_ACTIVITY_CHAIN",
                "DG_TIME_SCHEDULE",
                "DG_DISTANCE_PRIOR",
            )
        }
        unseen["DG_PARTICIPATION"].update(
            {str(key): int(value) for key, value in participation_unseen.items()}
        )
        backoff_levels: Counter[str] = Counter()
        backoff_fields: Counter[str] = Counter()
        day_rows: list[dict[str, Any]] = []
        trip_rows: list[dict[str, Any]] = []

        max_k = int(np.max(self.adapters.trip_count.support))
        if max_k < 1:
            raise ValueError("Trip-count support must be positive")

        for _, row in context.iterrows():
            row_dict = row.to_dict()
            row_id = str(row_dict["row_id"])
            household_id = str(row_dict["source_household_id"])
            person_id = str(row_dict["source_person_id"])
            static = {
                key: value
                for key, value in row_dict.items()
                if key not in {"row_id", "source_household_id", "source_person_id"}
            }

            part_seed = runtime_draw_seed(
                MASTER_SEED,
                runtime.scenario.scenario_id,
                person_id,
                "DG_PARTICIPATION",
                0,
            )
            part = self.adapters.participation.sample_one(
                _one_row(static, part_required), seed=part_seed
            )
            trip_day = bool(part["trip_day"])
            trip_count = 0
            activities: list[str] = []
            temporal_ok = True
            distance_ok = True

            if trip_day:
                count_seed = runtime_draw_seed(
                    MASTER_SEED,
                    runtime.scenario.scenario_id,
                    person_id,
                    "DG_TRIP_COUNT",
                    0,
                )
                count_required = list(self.adapters.trip_count.required_columns)
                count_frame = _one_row(static, count_required) if count_required else pd.DataFrame([{}])
                count = self.adapters.trip_count.sample_one(count_frame, seed=count_seed)
                trip_count = int(count["trip_count"])
                if trip_count < 1:
                    raise RuntimeError("Selected positive trip-count model produced trip_count < 1")

            if trip_count > 0:
                init_seed = runtime_draw_seed(
                    MASTER_SEED,
                    runtime.scenario.scenario_id,
                    person_id,
                    "DG_ACTIVITY_CHAIN",
                    0,
                )
                activities = [self.adapters.chain.sample_initial_activity(seed=init_seed)]

                for trip_index in range(1, trip_count + 1):
                    chain_state = propagated_chain_state(
                        static,
                        trip_count=trip_count,
                        prefix=activities,
                        remaining_trips=trip_count - trip_index,
                    )
                    level_index = _chain_selected_level(self.adapters.chain, chain_state)
                    backoff_levels[f"level_{level_index}"] += 1
                    if level_index > 0 and self.adapters.chain.record.candidate_id == "CHAIN_A":
                        skipped_fields = {
                            str(dimension)
                            for level in self.adapters.chain.model["levels"][:level_index]
                            for dimension in level["dimensions"]
                            if str(dimension) != "GLOBAL"
                        }
                        backoff_fields.update(skipped_fields)
                    chain_seed = runtime_draw_seed(
                        MASTER_SEED,
                        runtime.scenario.scenario_id,
                        person_id,
                        "DG_ACTIVITY_CHAIN",
                        2 * trip_index - 1,
                    )
                    sampled = self.adapters.chain.sample_transition(
                        pd.DataFrame([chain_state]), seed=chain_seed
                    )
                    activities.append(str(sampled["next_activity"]))

                previous_departure: int | None = None
                previous_arrival: int | None = None
                for trip_index in range(1, trip_count + 1):
                    time_state = propagated_time_state(
                        static,
                        trip_count=trip_count,
                        trip_index=trip_index,
                        origin_activity=activities[trip_index - 1],
                        destination_activity=activities[trip_index],
                        previous_departure_clock_minute=previous_departure,
                        previous_arrival_absolute_minute=previous_arrival,
                    )
                    time_seed = runtime_draw_seed(
                        MASTER_SEED,
                        runtime.scenario.scenario_id,
                        person_id,
                        f"DG_TIME_SCHEDULE::TRIP::{trip_index}",
                        0,
                    )
                    time_result, time_unseen = _time_b_full_chain_sample(
                        self.adapters.time,
                        time_state,
                        previous_arrival=previous_arrival,
                        trips_remaining=trip_count - trip_index,
                        seed=time_seed,
                    )
                    unseen["DG_TIME_SCHEDULE"].update(time_unseen)
                    departure = int(time_result["departure_clock_minute"])
                    arrival = int(time_result["arrival_absolute_minute"])
                    duration = int(time_result["duration_from_clock_min"])
                    previous_departure = departure
                    previous_arrival = arrival

                    distance_state = propagated_distance_state(
                        static,
                        trip_count=trip_count,
                        origin_activity=activities[trip_index - 1],
                        destination_activity=activities[trip_index],
                        departure_clock_minute=departure,
                        arrival_absolute_minute=arrival,
                        duration_from_clock_minute=duration,
                    )
                    distance_seed = runtime_draw_seed(
                        MASTER_SEED,
                        runtime.scenario.scenario_id,
                        person_id,
                        f"DG_DISTANCE_PRIOR::TRIP::{trip_index}",
                        0,
                    )
                    distance = self.adapters.distance.sample_one(
                        pd.DataFrame([distance_state]), seed=distance_seed
                    )
                    distance_km = float(distance["distance_prior_km"])
                    if not np.isfinite(distance_km) or distance_km <= 0:
                        distance_ok = False
                        raise RuntimeError("Selected distance adapter produced invalid distance")

                    trip_rows.append(
                        {
                            "pipeline": PIPELINE_LABEL,
                            "replicate_index": 0,
                            "row_id": row_id,
                            "source_household_id": household_id,
                            "source_person_id": person_id,
                            "trip_index": trip_index,
                            "trip_count": trip_count,
                            "origin_activity": activities[trip_index - 1],
                            "destination_activity": activities[trip_index],
                            "departure_clock_minute": departure,
                            "arrival_absolute_minute": arrival,
                            "duration_from_clock_min": duration,
                            "distance_prior_km": distance_km,
                        }
                    )

            day_rows.append(
                {
                    "pipeline": PIPELINE_LABEL,
                    "replicate_index": 0,
                    "row_id": row_id,
                    "source_household_id": household_id,
                    "source_person_id": person_id,
                    "trip_day": trip_day,
                    "trip_count": trip_count,
                    "final_activity": activities[-1] if activities else "",
                    "return_home": bool(activities and activities[-1] == "HOME"),
                    "temporal_chain_valid": temporal_ok,
                    "distance_chain_valid": distance_ok,
                }
            )

        days = pd.DataFrame(day_rows).sort_values(
            ["replicate_index", "row_id"], kind="mergesort"
        ).reset_index(drop=True)
        trip_columns = [
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
        ]
        trips = pd.DataFrame(trip_rows, columns=trip_columns)
        if not trips.empty:
            trips = trips.sort_values(
                ["replicate_index", "row_id", "trip_index"], kind="mergesort"
            ).reset_index(drop=True)

        support_audit = {
            "unseen_counts_by_component_and_field": {
                component: dict(sorted(counter.items())) for component, counter in unseen.items()
            },
            "chain_a_selected_level_counts": dict(sorted(backoff_levels.items())),
            "chain_a_backoff_counts_by_field": dict(sorted(backoff_fields.items())),
            "chain_a_backoff_events": int(
                sum(value for key, value in backoff_levels.items() if key != "level_0")
            ),
            "unhandled_runtime_categories": 0,
        }
        # No M2 draw, seed, state or sample changes occur after this boundary.
        days, trips, projection_audit, projection_metrics = project_m2_activity_frames(days, trips)
        support_audit["runtime_taxonomy_projection"] = projection_metrics
        return GenerationResult(
            day_rows=days,
            trip_rows=trips,
            support_audit=support_audit,
            artifact_validation=self.artifact_validation,
            projection_audit=projection_audit,
        )
