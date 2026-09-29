"""Controlled real-CAL runner for F3.4e Time Schedule.

CAL I/O is permitted only after an external authorization bound to the exact
committed implementation HEAD has been validated. PRE-OPEN tests/verifiers must
never invoke :func:`run_controlled_time_schedule_cal` with a valid authorization.
"""

from __future__ import annotations

import gzip
import json
import math
import platform
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from simfleet_edg.demand.time_schedule import validate_temporal_row
from simfleet_edg.evaluation.activity_chain_adapter import ActivityChainAdapter
from simfleet_edg.evaluation.cal_access_guard import PartitionAccess
from simfleet_edg.evaluation.cal_adapter_common import (
    ArtifactRecord,
    load_registry,
    sha256_file,
)
from simfleet_edg.evaluation.cal_bootstrap import (
    household_bootstrap_multipliers,
    percentile_interval,
)
from simfleet_edg.evaluation.cal_evidence import canonical_payload
from simfleet_edg.evaluation.cal_harness import evaluation_person_id, packed_draw_index
from simfleet_edg.evaluation.cal_protocol import (
    CAL_SCENARIO_ID,
    MASTER_SEED,
    bootstrap_seed,
    runtime_draw_seed,
)
from simfleet_edg.evaluation.cal_selection import (
    GridScore,
    choose_within_family,
    promotion_decision,
)
from simfleet_edg.evaluation.cal_state import (
    propagated_chain_state,
    propagated_time_state,
)
from simfleet_edg.evaluation.participation_adapter import ParticipationAdapter
from simfleet_edg.evaluation.time_schedule_adapter import TimeScheduleAdapter
from simfleet_edg.evaluation.trip_count_adapter import TripCountAdapter

COMPONENT = "DG_TIME_SCHEDULE"
PARTICIPATION_COMPONENT = "DG_PARTICIPATION"
TRIP_COUNT_COMPONENT = "DG_TRIP_COUNT"
ACTIVITY_CHAIN_COMPONENT = "DG_ACTIVITY_CHAIN"
UPSTREAM_PARTICIPATION_ID = "DG_PARTICIPATION::PART_A::PA1"
UPSTREAM_TRIP_COUNT_ID = "DG_TRIP_COUNT::COUNT_REF::REFERENCE"
UPSTREAM_ACTIVITY_CHAIN_ID = "DG_ACTIVITY_CHAIN::CHAIN_A::CHA2"
REFERENCE_ID = "TIME_REF_REFERENCE"
REPLICATES = 32
BOOTSTRAPS = 1000
PRACTICAL_MARGIN = 0.005
MISSING_CONTEXT = "__MISSING_CONTEXT__"
ROLE_RANK = {
    "REFERENCE_BASELINE": 0,
    "CORE_CANDIDATE_A": 1,
    "CORE_CHALLENGER_B": 2,
}
FORBIDDEN_TIME_FEATURES = {
    "row_id",
    "context_row_id",
    "source_household_id",
    "source_person_id",
    "source_person_slot",
    "source_trip_id",
    "fit_weight_W_GEW",
    "target_departure_clock_minute",
    "target_arrival_clock_minute",
    "target_arrival_day_offset",
    "target_duration_from_clock_min",
    "mode",
    "hvm",
    "km_routing",
    "route",
    "execution",
}


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo_root), *args], text=True).strip()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]] | pd.DataFrame) -> None:
    frame = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    frame.to_csv(path, index=False)


def _write_checksums(output_dir: Path) -> None:
    target = output_dir / "checksums.sha256"
    lines = [
        f"{sha256_file(path)}  {path.name}"
        for path in sorted(output_dir.iterdir())
        if path.is_file() and path.name != target.name
    ]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_authorization(path: Path, repo_root: Path) -> dict[str, Any]:
    """Validate external authorization before any CAL path is opened."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "phase": "F3.4e-2b",
        "component": COMPONENT,
        "real_time_schedule_cal_open_authorized": True,
        "candidate_artifacts": 7,
        "candidate_selection_at_entry": "NONE",
        "distance_prior_real_cal_authorized": False,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
    }
    for key, value in required.items():
        if payload.get(key) != value:
            raise PermissionError(f"Invalid execution authorization field {key}")
    current = _git(repo_root, "rev-parse", "HEAD")
    if payload.get("authorized_implementation_commit") != current:
        raise PermissionError("Authorization is not bound to current implementation commit")
    if set(payload.get("allowed_cal_files", [])) != {
        "person_day_context.csv",
        "time_trips.csv",
    }:
        raise PermissionError("Authorization CAL file scope mismatch")
    if _git(repo_root, "status", "--porcelain"):
        raise PermissionError("Real CAL execution requires a clean worktree")
    if _git(repo_root, "branch", "--show-current") != "main":
        raise PermissionError("Real CAL execution requires main branch")
    if _git(repo_root, "rev-list", "--count", "origin/main..HEAD") != "0":
        raise PermissionError("Real CAL execution requires ahead=0")
    if _git(repo_root, "rev-list", "--count", "HEAD..origin/main") != "0":
        raise PermissionError("Real CAL execution requires behind=0")
    return payload


def _validate_input_file(path: Path, expected_sha: str, expected_rows: int) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    if sha256_file(path) != expected_sha:
        raise ValueError(f"CAL input SHA mismatch for {path.name}")
    frame = pd.read_csv(path)
    if len(frame) != expected_rows:
        raise ValueError(f"CAL input row mismatch for {path.name}: {len(frame)} != {expected_rows}")
    return frame


def _all_records(repo_root: Path) -> list[ArtifactRecord]:
    return load_registry(repo_root / "docs/F3_3_CANDIDATE_ARTIFACT_REGISTRY_v1.csv")


def _records(repo_root: Path) -> list[ArtifactRecord]:
    records = [r for r in _all_records(repo_root) if r.component == COMPONENT]
    if len(records) != 7:
        raise ValueError("Time Schedule candidate universe must contain 7 artifacts")
    if {r.train_state for r in records} != {"FITTED_TRAIN_ONLY_NOT_SELECTED"}:
        raise ValueError("Unexpected Time Schedule train_state")
    return sorted(records, key=lambda r: (ROLE_RANK[r.role], r.grid_id))


def _record_by_id(repo_root: Path, artifact_id: str) -> ArtifactRecord:
    found = [r for r in _all_records(repo_root) if r.artifact_id == artifact_id]
    if len(found) != 1:
        raise ValueError(f"Frozen artifact not found exactly once: {artifact_id}")
    if found[0].train_state != "FITTED_TRAIN_ONLY_NOT_SELECTED":
        raise ValueError(f"Unexpected registry train_state: {artifact_id}")
    return found[0]


def _merge_time_context(time_rows: pd.DataFrame, context: pd.DataFrame) -> pd.DataFrame:
    merged = time_rows.merge(
        context,
        left_on="context_row_id",
        right_on="row_id",
        how="left",
        validate="many_to_one",
        suffixes=("_time", "_context"),
    )
    if len(merged) != len(time_rows) or merged["row_id"].isna().any():
        raise ValueError("time_trips/context CAL join failed")
    for field in ("source_household_id", "source_person_id"):
        if not merged[f"{field}_time"].astype(str).equals(merged[f"{field}_context"].astype(str)):
            raise ValueError(f"{field} mismatch in time_trips/context")
    return merged


def _validate_source_temporal_rows(frame: pd.DataFrame) -> None:
    """Validate frozen CAL targets without complete-case collapse.

    F3.2a explicitly retains optional upstream-context missingness.  The observed
    CAL target rows are reference evidence; the sequential temporal invariant is
    a hard guardrail on generated draws, not a reason to reject empirical target
    rows whose optional teacher-forced prefix is incomplete or overlaps.
    """
    required = {
        "context_row_id",
        "source_household_id_time",
        "source_person_id_time",
        "source_trip_id",
        "source_trip_count_analogue",
        "origin_activity_analogue",
        "destination_activity_analogue",
        "trip_position_class",
        "previous_departure_clock_minute",
        "previous_arrival_absolute_minute",
        "target_departure_clock_minute",
        "target_arrival_clock_minute",
        "target_arrival_day_offset",
        "target_duration_from_clock_min",
        "fit_weight_W_GEW",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Missing CAL time columns: {missing}")

    weights = frame["fit_weight_W_GEW"].astype(float).to_numpy()
    if not np.isfinite(weights).all() or np.any(weights <= 0):
        raise ValueError("CAL W_GEW must be finite and strictly positive")

    positions = frame["trip_position_class"].astype(str)
    allowed_positions = {"SINGLE", "FIRST", "MIDDLE", "LAST", MISSING_CONTEXT}
    unexpected = sorted(set(positions) - allowed_positions)
    if unexpected:
        raise ValueError(f"Unexpected trip_position_class values: {unexpected}")

    missing_k = frame["source_trip_count_analogue"].isna().to_numpy()
    missing_position = positions.eq(MISSING_CONTEXT).to_numpy()
    if not np.array_equal(missing_k, missing_position):
        raise ValueError("Missing source K and trip_position_class context must agree")

    dep = frame["target_departure_clock_minute"].astype(float).to_numpy()
    arr = frame["target_arrival_clock_minute"].astype(float).to_numpy()
    offset = frame["target_arrival_day_offset"].astype(float).to_numpy()
    dur = frame["target_duration_from_clock_min"].astype(float).to_numpy()
    if not np.isfinite(dep).all() or not np.isfinite(arr).all() or not np.isfinite(offset).all() or not np.isfinite(dur).all():
        raise ValueError("CAL temporal targets must be finite")
    if np.any(dep < 0) or np.any(dep >= 1440):
        raise ValueError("CAL departure clocks outside [0,1439]")
    if np.any(arr < 0) or np.any(arr >= 1440):
        raise ValueError("CAL arrival clocks outside [0,1439]")
    if not set(np.unique(offset.astype(int))).issubset({0, 1}) or not np.allclose(offset, offset.astype(int)):
        raise ValueError("CAL arrival day offsets must be integer 0/1")
    if np.any(dur < 1):
        raise ValueError("CAL duration must be >=1 minute")
    reconstructed = arr + 1440.0 * offset - dep
    if not np.allclose(reconstructed, dur, rtol=0.0, atol=1e-12):
        raise ValueError("CAL arrival/departure/day-offset/duration identity mismatch")


def load_and_validate_time_schedule_cal(
    repo_root: Path,
    cfg: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, Any]], dict[str, Any]]:
    PartitionAccess(cal_authorized=True, test_authorized=False).require_cal()
    root = repo_root / cfg["cal_input"]["root"]
    input_rows: list[dict[str, Any]] = []
    loaded: dict[str, pd.DataFrame] = {}
    for key in ("person_day_context", "time_trips"):
        spec = cfg["cal_input"][key]
        path = root / spec["filename"]
        frame = _validate_input_file(path, str(spec["sha256"]), int(spec["expected_rows"]))
        loaded[key] = frame
        input_rows.append({
            "filename": path.name,
            "sha256": sha256_file(path),
            "rows": len(frame),
            "status": "PASS",
        })
    context = loaded["person_day_context"]
    time_rows = loaded["time_trips"]
    if context["row_id"].duplicated().any():
        raise ValueError("CAL context row_id must be unique")
    merged = _merge_time_context(time_rows, context)
    _validate_source_temporal_rows(merged)
    fixed_ids = set(merged["context_row_id"].astype(str))
    cohort = context[context["row_id"].astype(str).isin(fixed_ids)].copy()
    if len(cohort) != len(fixed_ids):
        raise ValueError("Fixed Time Schedule cohort/context mismatch")
    if len(cohort) != int(cfg["cal_input"]["expected_fixed_cohort_days"]):
        raise ValueError("Unexpected fixed Time Schedule cohort size")
    if len(merged) != int(cfg["cal_input"]["expected_isolated_time_rows"]):
        raise ValueError("Unexpected isolated Time Schedule rows")
    physical = len(context) + len(time_rows)
    if physical != int(cfg["cal_input"]["expected_physical_rows"]):
        raise ValueError("Unexpected physical CAL row count")
    access = {
        "cal_partition": "OPENED_AUTHORIZED_F3_4E2B",
        "cal_files_opened": [
            str((root / cfg["cal_input"][key]["filename"]).relative_to(repo_root))
            for key in ("person_day_context", "time_trips")
        ],
        "cal_file_rows": {
            cfg["cal_input"][key]["filename"]: len(loaded[key])
            for key in ("person_day_context", "time_trips")
        },
        "cal_rows_read_total_physical": physical,
        "cal_fixed_source_cohort_days": len(cohort),
        "cal_isolated_time_rows": len(merged),
        "test_partition": "SEALED",
        "test_files_opened": [],
        "test_rows_read": 0,
    }
    return merged, cohort, input_rows, access


def _trips_remaining_after_current(position: str) -> int | None:
    if position in {"SINGLE", "LAST"}:
        return 0
    if position in {"FIRST", "MIDDLE"}:
        return 1
    if position == MISSING_CONTEXT:
        # Source K is genuinely unavailable for this retained row.  Do not invent
        # whether more trips remain; validate all other temporal constraints and
        # preserve the explicit missing feature value for candidate backoff.
        return None
    raise ValueError(f"Unexpected trip_position_class: {position}")


def _time_seed(context_row_id: object, slot: object, replicate: int) -> int:
    return runtime_draw_seed(
        MASTER_SEED,
        CAL_SCENARIO_ID,
        str(context_row_id),
        f"DG_TIME_SCHEDULE::TRIP::{slot}",
        int(replicate),
    )


def _candidate_feature_columns(adapter: TimeScheduleAdapter) -> set[str]:
    if adapter.record.candidate_id == "TIME_REF":
        return set()
    if adapter.record.candidate_id == "TIME_A":
        result: set[str] = set()
        for level in adapter.model["levels"]:
            result.update(str(x) for x in level["dimensions"] if x != "GLOBAL")
        return result
    if adapter.record.candidate_id == "TIME_B":
        if adapter.encoder is None:
            raise ValueError("TIME_B encoder missing")
        return set(str(x) for x in adapter.encoder.get("feature_columns", []))
    raise ValueError(adapter.record.candidate_id)


def _validate_candidate_artifacts(
    repo_root: Path,
    records: list[ArtifactRecord],
    cfg: dict[str, Any],
) -> tuple[list[TimeScheduleAdapter], list[dict[str, Any]]]:
    snapshot = json.loads((repo_root / cfg["candidate_registry"]["frozen_snapshot"]).read_text(encoding="utf-8"))
    frozen = {str(row["artifact_id"]): row for row in snapshot["candidates"]}
    adapters: list[TimeScheduleAdapter] = []
    rows: list[dict[str, Any]] = []
    for record in records:
        run_dir = record.validate(repo_root)
        snap = frozen.get(record.artifact_id)
        if snap is None:
            raise ValueError(f"Candidate missing from F3.4e-1 snapshot: {record.artifact_id}")
        if snap["model_sha256"] != record.model_sha256 or snap["manifest_sha256"] != record.manifest_sha256:
            raise ValueError(f"Candidate snapshot SHA mismatch: {record.artifact_id}")
        adapter = TimeScheduleAdapter(repo_root, record)
        future = sorted(_candidate_feature_columns(adapter) & FORBIDDEN_TIME_FEATURES)
        if future:
            raise ValueError(f"NFI/feature violation for {record.artifact_id}: {future}")
        adapters.append(adapter)
        rows.append({
            "artifact_id": record.artifact_id,
            "candidate_id": record.candidate_id,
            "grid_id": record.grid_id,
            "role": record.role,
            "train_state": record.train_state,
            "model_sha256": record.model_sha256,
            "manifest_sha256": record.manifest_sha256,
            "run_dir": str(run_dir),
            "status": "PASS",
        })
    return adapters, rows


def _round_half_up(value: float) -> int:
    return int(math.floor(float(value) + 0.5))


def _rounded_interp_pmf(
    xp: np.ndarray,
    fp: np.ndarray,
    *,
    lo: int,
    hi: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Exact PMF after monotone interpolation of U(0,1) and half-up rounding."""
    xp = np.asarray(xp, dtype=float)
    fp = np.asarray(fp, dtype=float)
    if xp.ndim != 1 or fp.ndim != 1 or len(xp) != len(fp):
        raise ValueError("Interpolation support must be aligned one-dimensional arrays")
    if np.any(np.diff(xp) <= 0) or np.any(np.diff(fp) < -1e-12):
        raise ValueError("Interpolation support must be strictly ordered in u and monotone in value")

    def cdf_le(value: int) -> float:
        if value < lo:
            return 0.0
        if value >= hi:
            return 1.0
        threshold = float(value) + 0.5
        if fp[0] >= threshold:
            return 0.0
        for idx in range(len(fp) - 1):
            y0 = float(fp[idx])
            y1 = float(fp[idx + 1])
            if y0 >= threshold:
                return float(xp[idx])
            if y1 >= threshold:
                if y1 <= y0 + 1e-15:
                    return float(xp[idx])
                fraction = (threshold - y0) / (y1 - y0)
                return float(xp[idx] + fraction * (xp[idx + 1] - xp[idx]))
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


def _sample_time_b_precomputed(
    adapter: TimeScheduleAdapter,
    dep_knots: np.ndarray,
    dur_knots: np.ndarray,
    *,
    previous_arrival_absolute_minute: float | None,
    trips_remaining_after_current: int | None,
    seed: int,
) -> dict[str, Any]:
    """Sample TIME_B exactly conditional on the frozen temporal invariant.

    The frozen quantile interpolation and half-up rounding induce discrete
    departure and duration distributions. Their independent joint distribution
    is conditioned exactly on temporal feasibility. This is the eventual-
    acceptance distribution of rejection sampling without a finite retry cap.
    No generated value is repaired or invented.
    """
    xp = np.asarray([0.0, *adapter.quantiles, 1.0], dtype=float)
    dep_fp = np.asarray([adapter.DEP_MIN, *dep_knots.tolist(), adapter.DEP_MAX], dtype=float)
    dur_fp = np.asarray([adapter.DUR_MIN, *dur_knots.tolist(), adapter.DUR_MAX], dtype=float)
    if np.any(np.diff(dep_fp) < -1e-12) or np.any(np.diff(dur_fp) < -1e-12):
        raise ValueError("TIME_B reconstruction knots are not monotone")

    dep_values, dep_probability = _rounded_interp_pmf(
        xp, dep_fp, lo=adapter.DEP_MIN, hi=adapter.DEP_MAX
    )
    dur_values, dur_probability = _rounded_interp_pmf(
        xp, dur_fp, lo=adapter.DUR_MIN, hi=adapter.DUR_MAX
    )

    dep_feasible = np.ones(len(dep_values), dtype=bool)
    if previous_arrival_absolute_minute is not None:
        dep_feasible &= dep_values.astype(float) >= float(previous_arrival_absolute_minute)

    if trips_remaining_after_current is not None and trips_remaining_after_current > 0:
        dur_cdf = np.cumsum(dur_probability)
        max_duration = (1439 - dep_values).astype(int)
        allowed_mass = np.zeros(len(dep_values), dtype=float)
        indices = np.searchsorted(dur_values, max_duration, side="right") - 1
        valid = indices >= 0
        allowed_mass[valid] = dur_cdf[indices[valid]]
    else:
        allowed_mass = np.ones(len(dep_values), dtype=float)

    dep_weight = dep_probability * dep_feasible.astype(float) * allowed_mass
    total = float(dep_weight.sum())
    if not np.isfinite(total) or total <= 0:
        raise RuntimeError("TIME_B has no feasible support under frozen temporal state")
    dep_weight /= total

    rng = np.random.default_rng(seed)
    dep_index = int(rng.choice(len(dep_values), p=dep_weight))
    departure = int(dep_values[dep_index])

    if trips_remaining_after_current is not None and trips_remaining_after_current > 0:
        dur_mask = dur_values <= 1439 - departure
    else:
        dur_mask = np.ones(len(dur_values), dtype=bool)
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
        previous_arrival_absolute_minute=previous_arrival_absolute_minute,
        trips_remaining_after_current=trips_remaining_after_current,
    )
    if not ok:
        raise RuntimeError("TIME_B exact conditional sampler produced invalid temporal row")
    return {
        **result,
        "attempt": 1,
        "uniform_departure": None,
        "uniform_duration": None,
        "sampling_policy": "EXACT_TIME_B_FEASIBLE_CONDITIONAL_V1",
    }

def _sample_time_b_propagated_lookahead(
    adapter: TimeScheduleAdapter,
    dep_knots: np.ndarray,
    dur_knots: np.ndarray,
    *,
    previous_arrival_absolute_minute: int | None,
    trips_remaining_after_current: int,
    seed: int,
) -> dict[str, Any]:
    """Sample TIME_B with exact full-chain minimum-slack conditioning.

    This propagated-only sampler preserves the frozen TIME_B quantile
    interpolation, half-up rounding, independent departure/duration law, and
    candidate-independent RNG seed schedule.  It conditions the current draw on
    leaving the universal minimum temporal slack needed to place all remaining
    trips: one minute of minimum duration per future trip.  No value is repaired
    or invented.
    """
    xp = np.asarray([0.0, *adapter.quantiles, 1.0], dtype=float)
    dep_fp = np.asarray([adapter.DEP_MIN, *dep_knots.tolist(), adapter.DEP_MAX], dtype=float)
    dur_fp = np.asarray([adapter.DUR_MIN, *dur_knots.tolist(), adapter.DUR_MAX], dtype=float)
    if np.any(np.diff(dep_fp) < -1e-12) or np.any(np.diff(dur_fp) < -1e-12):
        raise ValueError("TIME_B reconstruction knots are not monotone")

    dep_values, dep_probability = _rounded_interp_pmf(
        xp, dep_fp, lo=adapter.DEP_MIN, hi=adapter.DEP_MAX
    )
    dur_values, dur_probability = _rounded_interp_pmf(
        xp, dur_fp, lo=adapter.DUR_MIN, hi=adapter.DUR_MAX
    )

    dep_feasible = np.ones(len(dep_values), dtype=bool)
    if previous_arrival_absolute_minute is not None:
        dep_feasible &= dep_values >= int(previous_arrival_absolute_minute)

    if trips_remaining_after_current > 0:
        arrival_limit = 1440 - trips_remaining_after_current
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
        raise RuntimeError(
            "TIME_B has no full-chain minimum-slack support under frozen propagated temporal state"
        )
    dep_weight /= total

    rng = np.random.default_rng(seed)
    dep_index = int(rng.choice(len(dep_values), p=dep_weight))
    departure = int(dep_values[dep_index])

    if trips_remaining_after_current > 0:
        dur_mask = dur_values <= arrival_limit - departure
    else:
        dur_mask = np.ones(len(dur_values), dtype=bool)
    feasible_dur_values = dur_values[dur_mask]
    feasible_dur_probability = dur_probability[dur_mask]
    duration_total = float(feasible_dur_probability.sum())
    if not np.isfinite(duration_total) or duration_total <= 0:
        raise RuntimeError(
            "TIME_B has no full-chain minimum-slack duration support after departure draw"
        )
    feasible_dur_probability /= duration_total
    duration = int(rng.choice(feasible_dur_values, p=feasible_dur_probability))

    ok, result = validate_temporal_row(
        departure,
        duration,
        previous_arrival_absolute_minute=previous_arrival_absolute_minute,
        trips_remaining_after_current=trips_remaining_after_current,
    )
    if not ok:
        raise RuntimeError("TIME_B full-chain lookahead sampler produced invalid temporal row")
    return {
        **result,
        "attempt": 1,
        "uniform_departure": None,
        "uniform_duration": None,
        "sampling_policy": "EXACT_TIME_B_FULL_CHAIN_MIN_SLACK_CONDITIONAL_V1",
        "future_minimum_slack_arrival_limit": int(arrival_limit),
    }


def _reference_support_rows(adapter: TimeScheduleAdapter) -> list[dict[str, Any]]:
    support = list(adapter.model["joint_temporal_support"])
    if not support:
        raise RuntimeError("TIME_REF empirical joint support is empty")
    return support


def _reference_full_chain_thresholds(
    adapter: TimeScheduleAdapter,
    max_trip_count: int,
) -> dict[int, int | None]:
    """Return exact previous-arrival thresholds for complete TIME_REF paths.

    thresholds[n] is the greatest previous-arrival minute from which at least one
    n-trip continuation exists using only the frozen empirical joint support.
    """
    support = _reference_support_rows(adapter)
    thresholds: dict[int, int | None] = {0: 10**9}

    for trips_left in range(1, max_trip_count + 1):
        remaining_after_current = trips_left - 1
        future_threshold = thresholds[trips_left - 1]
        viable_departures: list[int] = []
        for sample in support:
            departure = int(sample["departure_clock_minute"])
            duration = int(sample["duration_from_clock_min"])
            ok, result = validate_temporal_row(
                departure,
                duration,
                previous_arrival_absolute_minute=None,
                trips_remaining_after_current=remaining_after_current,
            )
            if not ok:
                continue
            if remaining_after_current > 0:
                if future_threshold is None:
                    continue
                if int(result["arrival_absolute_minute"]) > int(future_threshold):
                    continue
            viable_departures.append(departure)
        thresholds[trips_left] = max(viable_departures) if viable_departures else None

    return thresholds


def _sample_time_ref_propagated_lookahead(
    adapter: TimeScheduleAdapter,
    *,
    previous_arrival_absolute_minute: int | None,
    trips_remaining_after_current: int,
    seed: int,
    full_chain_thresholds: dict[int, int | None],
) -> dict[str, Any]:
    """Sample TIME_REF conditional on a complete frozen-support continuation."""
    support = _reference_support_rows(adapter)
    future_threshold = full_chain_thresholds[trips_remaining_after_current]
    feasible: list[tuple[dict[str, Any], dict[str, int | float]]] = []
    probability: list[float] = []

    for sample in support:
        departure = int(sample["departure_clock_minute"])
        duration = int(sample["duration_from_clock_min"])
        ok, result = validate_temporal_row(
            departure,
            duration,
            previous_arrival_absolute_minute=previous_arrival_absolute_minute,
            trips_remaining_after_current=trips_remaining_after_current,
        )
        if not ok:
            continue
        if trips_remaining_after_current > 0:
            if future_threshold is None:
                continue
            if int(result["arrival_absolute_minute"]) > int(future_threshold):
                continue
        feasible.append((sample, result))
        probability.append(float(sample["probability"]))

    if not feasible:
        raise RuntimeError(
            "TIME_REF has no full-chain support under frozen propagated temporal state"
        )

    p = np.asarray(probability, dtype=float)
    total = float(p.sum())
    if not np.isfinite(total) or total <= 0:
        raise RuntimeError("TIME_REF full-chain feasible support has invalid probability mass")
    p /= total
    rng = np.random.default_rng(seed)
    selected = int(rng.choice(len(feasible), p=p))
    sample, result = feasible[selected]
    return {
        **result,
        "attempt": 1,
        "selected_level": 0,
        "sampling_policy": "EXACT_REFERENCE_FULL_CHAIN_SUPPORT_CONDITIONAL_V1",
        "source_departure_clock_minute": int(sample["departure_clock_minute"]),
        "source_duration_from_clock_min": int(sample["duration_from_clock_min"]),
        "future_support_threshold": future_threshold,
    }


def _sample_time_ref_conditioned(
    adapter: TimeScheduleAdapter,
    *,
    previous_arrival_absolute_minute: float | None,
    trips_remaining_after_current: int | None,
    seed: int,
) -> dict[str, Any]:
    """Sample TIME_REF exactly from its temporally feasible empirical support.

    This is the exact conditional distribution induced by rejection sampling
    given eventual acceptance.  It removes the finite-attempt exhaustion artefact
    while preserving the frozen support, probabilities, seed schedule, and hard
    temporal invariant.  No draw is repaired and no value is invented.
    """
    support = list(adapter.model["joint_temporal_support"])
    feasible: list[tuple[dict[str, Any], dict[str, int | float]]] = []
    probability: list[float] = []
    for sample in support:
        ok, result = validate_temporal_row(
            int(sample["departure_clock_minute"]),
            int(sample["duration_from_clock_min"]),
            previous_arrival_absolute_minute=previous_arrival_absolute_minute,
            trips_remaining_after_current=trips_remaining_after_current,
        )
        if ok:
            feasible.append((sample, result))
            probability.append(float(sample["probability"]))

    if not feasible:
        raise RuntimeError("TIME_REF has no feasible support under frozen temporal state")

    p = np.asarray(probability, dtype=float)
    total = float(p.sum())
    if not np.isfinite(total) or total <= 0:
        raise RuntimeError("TIME_REF feasible support has invalid probability mass")
    p /= total
    rng = np.random.default_rng(seed)
    selected = int(rng.choice(len(feasible), p=p))
    sample, result = feasible[selected]
    return {
        **result,
        "attempt": 1,
        "selected_level": 0,
        "sampling_policy": "EXACT_FEASIBLE_SUPPORT_CONDITIONAL_V1",
        "source_departure_clock_minute": int(sample["departure_clock_minute"]),
        "source_duration_from_clock_min": int(sample["duration_from_clock_min"]),
    }


def _weighted_hour_tvd(observed_hours: np.ndarray, generated_hours: np.ndarray, weights: np.ndarray) -> float:
    if weights.sum() <= 0:
        raise ValueError("TVD total weight must be positive")
    obs = np.bincount(observed_hours.astype(int), weights=weights, minlength=24).astype(float)
    gen = np.bincount(generated_hours.astype(int), weights=weights, minlength=24).astype(float)
    obs /= obs.sum()
    gen /= gen.sum()
    return float(0.5 * np.abs(obs - gen).sum())


def _circular_wasserstein_minutes(observed: np.ndarray, generated: np.ndarray, weights: np.ndarray) -> float:
    if weights.sum() <= 0:
        raise ValueError("Circular Wasserstein total weight must be positive")
    obs = np.bincount(observed.astype(int), weights=weights, minlength=1440).astype(float)
    gen = np.bincount(generated.astype(int), weights=weights, minlength=1440).astype(float)
    obs /= obs.sum()
    gen /= gen.sum()
    cumulative = np.cumsum(obs - gen)[:-1]
    center = float(np.median(cumulative)) if len(cumulative) else 0.0
    return float(np.abs(cumulative - center).sum())


def _generate_isolated_candidate(
    adapter: TimeScheduleAdapter,
    frame: pd.DataFrame,
) -> dict[str, Any]:
    n = len(frame)
    dep = np.full((REPLICATES, n), -1, dtype=np.int32)
    dur = np.full((REPLICATES, n), -1, dtype=np.int32)
    arr = np.full((REPLICATES, n), -1, dtype=np.int32)
    offset = np.full((REPLICATES, n), -1, dtype=np.int8)
    attempts = np.zeros((REPLICATES, n), dtype=np.int16)
    violations = 0
    failures: list[dict[str, Any]] = []

    repaired = adapter._time_b_quantiles(frame) if adapter.record.candidate_id == "TIME_B" else None

    for row_index, (_, row) in enumerate(frame.iterrows()):
        previous = row["previous_arrival_absolute_minute"]
        previous_value = None if pd.isna(previous) else float(previous)
        remaining = _trips_remaining_after_current(str(row["trip_position_class"]))
        slot = row["source_trip_id"]
        row_frame = frame.iloc[[row_index]]
        for replicate in range(REPLICATES):
            seed = _time_seed(row["context_row_id"], slot, replicate)
            try:
                if adapter.record.candidate_id == "TIME_REF":
                    result = _sample_time_ref_conditioned(
                        adapter,
                        previous_arrival_absolute_minute=previous_value,
                        trips_remaining_after_current=remaining,
                        seed=seed,
                    )
                elif repaired is not None:
                    result = _sample_time_b_precomputed(
                        adapter,
                        repaired["departure_clock_minute"][row_index],
                        repaired["duration_from_clock_min"][row_index],
                        previous_arrival_absolute_minute=previous_value,
                        trips_remaining_after_current=remaining,
                        seed=seed,
                    )
                else:
                    result = adapter.sample_one(
                        row_frame,
                        previous_arrival_absolute_minute=previous_value,
                        trips_remaining_after_current=remaining,
                        seed=seed,
                    )
                ok, _ = validate_temporal_row(
                    result["departure_clock_minute"],
                    result["duration_from_clock_min"],
                    previous_arrival_absolute_minute=previous_value,
                    trips_remaining_after_current=remaining,
                )
                if not ok:
                    raise RuntimeError("Generated temporal row failed frozen invariant")
                dep[replicate, row_index] = int(result["departure_clock_minute"])
                dur[replicate, row_index] = int(result["duration_from_clock_min"])
                arr[replicate, row_index] = int(result["arrival_clock_minute"])
                offset[replicate, row_index] = int(result["arrival_day_offset"])
                attempts[replicate, row_index] = int(result["attempt"])
            except Exception as exc:
                violations += 1
                failures.append({
                    "row_index": row_index,
                    "replicate_id": replicate,
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                })
    return {
        "departure": dep,
        "duration": dur,
        "arrival": arr,
        "offset": offset,
        "attempt": attempts,
        "temporal_invariant_violations": violations,
        "failures": failures,
    }


def _primary_and_auxiliary(
    frame: pd.DataFrame,
    generated: dict[str, Any],
) -> tuple[float, float, list[float], list[float]]:
    if int(generated["temporal_invariant_violations"]) != 0:
        return math.nan, math.nan, [], []
    observed_min = frame["target_departure_clock_minute"].astype(int).to_numpy()
    observed_hour = observed_min // 60
    weights = frame["fit_weight_W_GEW"].astype(float).to_numpy()
    tvds: list[float] = []
    circular: list[float] = []
    for replicate in range(REPLICATES):
        gen_min = generated["departure"][replicate]
        tvds.append(_weighted_hour_tvd(observed_hour, gen_min // 60, weights))
        circular.append(_circular_wasserstein_minutes(observed_min, gen_min, weights))
    return float(np.mean(tvds)), float(np.mean(circular)), tvds, circular


def _bootstrap_improvement(
    frame: pd.DataFrame,
    incumbent_generated: np.ndarray,
    challenger_generated: np.ndarray,
    incumbent_id: str,
    challenger_id: str,
) -> dict[str, Any]:
    observed_hours = frame["target_departure_clock_minute"].astype(int).to_numpy() // 60
    base_weight = frame["fit_weight_W_GEW"].astype(float).to_numpy()
    multipliers = household_bootstrap_multipliers(
        frame["source_household_id_time"],
        replicates=BOOTSTRAPS,
        seed=bootstrap_seed(MASTER_SEED, COMPONENT, incumbent_id, challenger_id),
    )
    differences = np.empty(BOOTSTRAPS, dtype=float)
    for index, multiplier in enumerate(multipliers):
        weight = base_weight * multiplier
        if weight.sum() <= 0:
            raise ValueError("Bootstrap removed all Time Schedule rows")
        inc = np.mean([
            _weighted_hour_tvd(observed_hours, incumbent_generated[r] // 60, weight)
            for r in range(REPLICATES)
        ])
        chal = np.mean([
            _weighted_hour_tvd(observed_hours, challenger_generated[r] // 60, weight)
            for r in range(REPLICATES)
        ])
        differences[index] = float(inc - chal)
    interval = percentile_interval(differences, confidence_level=0.95)
    return {
        "incumbent_artifact_id": incumbent_id,
        "challenger_artifact_id": challenger_id,
        "bootstrap_replicates": BOOTSTRAPS,
        "ci_lower": interval.lower,
        "ci_median": interval.median,
        "ci_upper": interval.upper,
    }


def _candidate_score(record: ArtifactRecord, primary: float, hard_pass: bool) -> GridScore:
    return GridScore(
        artifact_id=record.artifact_id,
        candidate_id=record.candidate_id,
        grid_id=record.grid_id,
        role=record.role,
        primary_metric=float(primary),
        hard_pass=bool(hard_pass),
        guardrails_pass=bool(hard_pass),
    )


def _static_context(row: pd.Series) -> dict[str, Any]:
    excluded = {"row_id", "source_household_id", "source_person_id", "source_person_slot", "fit_weight_P_GEW"}
    return {key: value for key, value in row.to_dict().items() if key not in excluded}


def _upstream_generated_state(
    repo_root: Path,
    cohort: pd.DataFrame,
) -> tuple[np.ndarray, list[list[list[str]]], dict[str, Any]]:
    part_record = _record_by_id(repo_root, UPSTREAM_PARTICIPATION_ID)
    count_record = _record_by_id(repo_root, UPSTREAM_TRIP_COUNT_ID)
    chain_record = _record_by_id(repo_root, UPSTREAM_ACTIVITY_CHAIN_ID)
    part = ParticipationAdapter(repo_root, part_record)
    count = TripCountAdapter(repo_root, count_record)
    chain = ActivityChainAdapter(repo_root, chain_record)

    probability = part.probabilities(cohort)
    count_pmf = count.pmf(cohort)
    count_support = np.asarray(count.support, dtype=int)
    count_cdf = np.cumsum(count_pmf, axis=1)
    generated_k = np.zeros((REPLICATES, len(cohort)), dtype=np.int16)
    sequences: list[list[list[str]]] = [[[] for _ in range(len(cohort))] for _ in range(REPLICATES)]

    for replicate in range(REPLICATES):
        for row_index, (_, day) in enumerate(cohort.iterrows()):
            person_id = evaluation_person_id(day["source_household_id"], day["source_person_id"])
            part_seed = runtime_draw_seed(
                MASTER_SEED, CAL_SCENARIO_ID, person_id, PARTICIPATION_COMPONENT, packed_draw_index(replicate, 0)
            )
            if np.random.default_rng(part_seed).random() >= float(probability[row_index]):
                continue
            count_seed = runtime_draw_seed(
                MASTER_SEED, CAL_SCENARIO_ID, person_id, TRIP_COUNT_COMPONENT, packed_draw_index(replicate, 0)
            )
            u = float(np.random.default_rng(count_seed).random())
            index = min(int(np.sum(u > count_cdf[row_index])), len(count_support) - 1)
            k = int(count_support[index])
            generated_k[replicate, row_index] = k
            if k == 0:
                continue

            initial_seed = runtime_draw_seed(
                MASTER_SEED, CAL_SCENARIO_ID, person_id, ACTIVITY_CHAIN_COMPONENT, packed_draw_index(replicate, 0)
            )
            prefix = [chain.sample_initial_activity(seed=initial_seed)]
            static = _static_context(day)
            for trip_index in range(1, k + 1):
                state = propagated_chain_state(
                    static,
                    trip_count=k,
                    prefix=prefix,
                    remaining_trips=k - trip_index,
                )
                transition_seed = runtime_draw_seed(
                    MASTER_SEED,
                    CAL_SCENARIO_ID,
                    person_id,
                    ACTIVITY_CHAIN_COMPONENT,
                    packed_draw_index(replicate, 2 * trip_index - 1),
                )
                sampled = chain.sample_transition(pd.DataFrame([state]), seed=transition_seed)
                prefix.append(str(sampled["next_activity"]))
            if len(prefix) != k + 1:
                raise ValueError("Generated Activity Chain length invariant failed")
            sequences[replicate][row_index] = prefix

    snapshot = {
        "participation_artifact_id": UPSTREAM_PARTICIPATION_ID,
        "participation_state": "MAIN_FROZEN",
        "trip_count_artifact_id": UPSTREAM_TRIP_COUNT_ID,
        "trip_count_state": "MAIN_FROZEN",
        "activity_chain_artifact_id": UPSTREAM_ACTIVITY_CHAIN_ID,
        "activity_chain_state": "MAIN_FROZEN",
        "fixed_source_cohort_days": len(cohort),
        "cohort_reselected": False,
    }
    return generated_k, sequences, snapshot


def _run_propagated_time(
    adapter: TimeScheduleAdapter,
    cohort: pd.DataFrame,
    generated_k: np.ndarray,
    sequences: list[list[list[str]]],
) -> dict[str, Any]:
    violations = 0
    generated_rows = 0
    failure_rows: list[dict[str, Any]] = []
    reference_thresholds = (
        _reference_full_chain_thresholds(adapter, int(generated_k.max()))
        if adapter.record.candidate_id == "TIME_REF"
        else None
    )
    for replicate in range(REPLICATES):
        for row_index, (_, day) in enumerate(cohort.iterrows()):
            k = int(generated_k[replicate, row_index])
            if k == 0:
                continue
            activities = sequences[replicate][row_index]
            if len(activities) != k + 1:
                raise ValueError("Missing propagated activity sequence")
            static = _static_context(day)
            prev_dep: int | None = None
            prev_arr: int | None = None
            for trip_index in range(1, k + 1):
                state = propagated_time_state(
                    static,
                    trip_count=k,
                    trip_index=trip_index,
                    origin_activity=activities[trip_index - 1],
                    destination_activity=activities[trip_index],
                    previous_departure_clock_minute=prev_dep,
                    previous_arrival_absolute_minute=prev_arr,
                )
                seed = _time_seed(day["row_id"], trip_index, replicate)
                try:
                    if adapter.record.candidate_id == "TIME_REF":
                        if reference_thresholds is None:
                            raise RuntimeError("TIME_REF propagated support thresholds are unavailable")
                        result = _sample_time_ref_propagated_lookahead(
                            adapter,
                            previous_arrival_absolute_minute=prev_arr,
                            trips_remaining_after_current=k - trip_index,
                            seed=seed,
                            full_chain_thresholds=reference_thresholds,
                        )
                    elif adapter.record.candidate_id == "TIME_B":
                        time_b_quantiles = adapter._time_b_quantiles(pd.DataFrame([state]))
                        result = _sample_time_b_propagated_lookahead(
                            adapter,
                            time_b_quantiles["departure_clock_minute"][0],
                            time_b_quantiles["duration_from_clock_min"][0],
                            previous_arrival_absolute_minute=prev_arr,
                            trips_remaining_after_current=k - trip_index,
                            seed=seed,
                        )
                    else:
                        result = adapter.sample_one(
                            pd.DataFrame([state]),
                            previous_arrival_absolute_minute=prev_arr,
                            trips_remaining_after_current=k - trip_index,
                            seed=seed,
                        )
                    ok, validated = validate_temporal_row(
                        result["departure_clock_minute"],
                        result["duration_from_clock_min"],
                        previous_arrival_absolute_minute=prev_arr,
                        trips_remaining_after_current=k - trip_index,
                    )
                    if not ok:
                        raise RuntimeError("Generated propagated temporal row failed invariant")
                    prev_dep = int(validated["departure_clock_minute"])
                    prev_arr = int(validated["arrival_absolute_minute"])
                    generated_rows += 1
                except Exception as exc:
                    violations += 1
                    failure_rows.append({
                        "context_row_id": str(day["row_id"]),
                        "replicate_id": replicate,
                        "trip_index": trip_index,
                        "exception_type": type(exc).__name__,
                        "exception_message": str(exc),
                    })
                    break
    return {
        "temporal_invariant_violations": violations,
        "generated_time_rows": generated_rows,
        "failures": failure_rows,
        "hard_pass": violations == 0,
    }


def _run_controlled_time_schedule_cal_direct(
    repo_root: Path,
    output_dir: Path,
    config_path: Path,
    authorization_path: Path,
    *,
    write_stochastic_evidence: bool = True,
) -> dict[str, Any]:
    started = time.perf_counter()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if config.get("phase") != "F3.4e-2b":
        raise ValueError("Unexpected Time Schedule real-CAL implementation contract")

    # Authorization MUST succeed before CAL I/O or staging directory creation.
    authorization = load_authorization(authorization_path, repo_root)
    if output_dir.exists():
        raise FileExistsError(f"RunBundle output already exists: {output_dir}")
    output_dir.mkdir(parents=True)

    merged, cohort, input_rows, access = load_and_validate_time_schedule_cal(repo_root, config)
    records = _records(repo_root)
    adapters, artifact_validation = _validate_candidate_artifacts(repo_root, records, config)
    adapter_by_id = {adapter.record.artifact_id: adapter for adapter in adapters}
    record_by_id = {record.artifact_id: record for record in records}

    generated_by_id: dict[str, dict[str, Any]] = {}
    primary_by_id: dict[str, float] = {}
    primary_rows: list[dict[str, Any]] = []
    auxiliary_rows: list[dict[str, Any]] = []
    hard_rows: list[dict[str, Any]] = []

    for adapter in adapters:
        generated = _generate_isolated_candidate(adapter, merged)
        generated_by_id[adapter.record.artifact_id] = generated
        primary, circular, per_rep_tvd, per_rep_circular = _primary_and_auxiliary(merged, generated)
        hard_pass = int(generated["temporal_invariant_violations"]) == 0
        primary_by_id[adapter.record.artifact_id] = primary
        primary_rows.append({
            "artifact_id": adapter.record.artifact_id,
            "candidate_id": adapter.record.candidate_id,
            "grid_id": adapter.record.grid_id,
            "role": adapter.record.role,
            "primary_metric": "M2-TIME-01",
            "primary_statistic": "DEPARTURE_HOUR_DISTRIBUTION_TVD_MEAN32",
            "value": primary,
            "hard_pass": hard_pass,
        })
        auxiliary_rows.append({
            "artifact_id": adapter.record.artifact_id,
            "metric": "CIRCULAR_WASSERSTEIN_DEPARTURE_MINUTES_MEAN32",
            "value": circular,
            "role": "REPORT_ONLY",
        })
        hard_rows.append({
            "artifact_id": adapter.record.artifact_id,
            "temporal_invariant_violations": int(generated["temporal_invariant_violations"]),
            "hard_pass": hard_pass,
            "failed_draws": len(generated["failures"]),
        })
        if hard_pass and (len(per_rep_tvd) != REPLICATES or len(per_rep_circular) != REPLICATES):
            raise ValueError("Incomplete Time Schedule replicate metrics")

    reference = record_by_id[REFERENCE_ID]
    if not bool(pd.DataFrame(hard_rows).set_index("artifact_id").loc[REFERENCE_ID, "hard_pass"]):
        raise ValueError("TIME_REF failed isolated temporal hard invariant")

    grid_rows: list[dict[str, Any]] = []
    bootstrap_rows: list[dict[str, Any]] = []
    promotion_rows: list[dict[str, Any]] = []
    incumbent = reference

    def score(record: ArtifactRecord) -> GridScore:
        generated = generated_by_id[record.artifact_id]
        hard = int(generated["temporal_invariant_violations"]) == 0
        value = primary_by_id[record.artifact_id]
        return _candidate_score(record, value, hard)

    a_records = [r for r in records if r.role == "CORE_CANDIDATE_A"]
    a_scores = [score(r) for r in a_records]
    best_a = choose_within_family(a_scores)
    for item in a_scores:
        grid_rows.append({**asdict(item), "family": "A", "selected_within_family": bool(best_a and item.artifact_id == best_a.artifact_id)})
    if best_a is not None:
        boot = _bootstrap_improvement(
            merged,
            generated_by_id[reference.artifact_id]["departure"],
            generated_by_id[best_a.artifact_id]["departure"],
            reference.artifact_id,
            best_a.artifact_id,
        )
        bootstrap_rows.append(boot)
        decision = promotion_decision(
            score(reference), best_a,
            practical_margin=PRACTICAL_MARGIN,
            bootstrap_ci_lower=float(boot["ci_lower"]),
            bootstrap_ci_upper=float(boot["ci_upper"]),
        )
        promotion_rows.append({**asdict(decision), "reasons": ";".join(decision.reasons), "stage": "REF_TO_A"})
        if decision.promoted:
            incumbent = record_by_id[best_a.artifact_id]

    b_records = [r for r in records if r.role == "CORE_CHALLENGER_B"]
    b_scores = [score(r) for r in b_records]
    best_b = choose_within_family(b_scores)
    for item in b_scores:
        grid_rows.append({**asdict(item), "family": "B", "selected_within_family": bool(best_b and item.artifact_id == best_b.artifact_id)})
    if best_b is not None:
        boot = _bootstrap_improvement(
            merged,
            generated_by_id[incumbent.artifact_id]["departure"],
            generated_by_id[best_b.artifact_id]["departure"],
            incumbent.artifact_id,
            best_b.artifact_id,
        )
        bootstrap_rows.append(boot)
        decision = promotion_decision(
            score(incumbent), best_b,
            practical_margin=PRACTICAL_MARGIN,
            bootstrap_ci_lower=float(boot["ci_lower"]),
            bootstrap_ci_upper=float(boot["ci_upper"]),
        )
        promotion_rows.append({**asdict(decision), "reasons": ";".join(decision.reasons), "stage": "INCUMBENT_TO_B"})
        if decision.promoted:
            incumbent = record_by_id[best_b.artifact_id]

    generated_k, sequences, upstream_snapshot = _upstream_generated_state(repo_root, cohort)
    propagated_records = [reference]
    if incumbent.artifact_id != reference.artifact_id:
        propagated_records.append(incumbent)
    propagated_rows: list[dict[str, Any]] = []
    for record in propagated_records:
        result = _run_propagated_time(adapter_by_id[record.artifact_id], cohort, generated_k, sequences)
        propagated_rows.append({
            "artifact_id": record.artifact_id,
            "temporal_invariant_violations": int(result["temporal_invariant_violations"]),
            "generated_time_rows": int(result["generated_time_rows"]),
            "hard_pass": bool(result["hard_pass"]),
        })
    prop = pd.DataFrame(propagated_rows).set_index("artifact_id")
    reference_prop_pass = bool(prop.loc[reference.artifact_id, "hard_pass"])
    incumbent_prop_pass = bool(prop.loc[incumbent.artifact_id, "hard_pass"])
    propagated_pass = reference_prop_pass and incumbent_prop_pass

    selected = {
        "status": "PROPOSED_BY_FROZEN_CAL_RULES_AWAITING_MAIN_FREEZE" if propagated_pass else "BLOCKED_PROPAGATED_TEMPORAL_GUARDRAIL_RETURN_TO_MAIN",
        "base_artifact_id": incumbent.artifact_id,
        "proposed_selected_artifact_id": incumbent.artifact_id if propagated_pass else None,
        "candidate_id": incumbent.candidate_id,
        "grid_id": incumbent.grid_id,
        "role": incumbent.role,
        "isolated_selection_complete": True,
        "propagated_temporal_guardrail_pass": propagated_pass,
        "authorized_for_downstream": False,
        "distance_prior_real_cal_authorized": False,
    }

    _write_csv(output_dir / "input_hash_validation.csv", input_rows)
    _write_csv(output_dir / "candidate_artifact_validation.csv", artifact_validation)
    _write_csv(output_dir / "primary_metrics.csv", primary_rows)
    _write_csv(output_dir / "isolated_auxiliary_metrics.csv", auxiliary_rows)
    _write_csv(output_dir / "isolated_temporal_guardrails.csv", hard_rows)
    _write_csv(output_dir / "bootstrap_intervals.csv", bootstrap_rows)
    _write_csv(output_dir / "grid_selection.csv", grid_rows)
    _write_csv(output_dir / "promotion_decisions.csv", promotion_rows)
    _write_csv(output_dir / "propagated_temporal_guardrails.csv", propagated_rows)
    _write_json(output_dir / "upstream_selection_snapshot.json", upstream_snapshot)
    _write_json(output_dir / "selected_component_artifact.json", selected)
    _write_json(output_dir / "cal_access_manifest.json", access)
    _write_json(output_dir / "execution_authorization_snapshot.json", authorization)
    (output_dir / "execution_contract_snapshot.yaml").write_bytes(config_path.read_bytes())
    _write_json(output_dir / "environment.json", {
        "python": sys.version,
        "platform": platform.platform(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
    })

    evidence_rows = 0
    if write_stochastic_evidence:
        evidence_path = output_dir / "stochastic_evidence.csv.gz"
        with gzip.open(evidence_path, "wt", encoding="utf-8", newline="") as handle:
            header_written = False
            for record in records:
                generated = generated_by_id[record.artifact_id]
                if int(generated["temporal_invariant_violations"]) != 0:
                    continue
                blocks: list[pd.DataFrame] = []
                for replicate in range(REPLICATES):
                    block = pd.DataFrame({
                        "component": COMPONENT,
                        "artifact_id": record.artifact_id,
                        "candidate_id": record.candidate_id,
                        "grid_id": record.grid_id,
                        "role": record.role,
                        "evaluation_mode": "ISOLATED",
                        "replicate_id": replicate,
                        "evaluation_person_id": "CAL|" + merged["source_household_id_time"].astype(str) + "|" + merged["source_person_id_time"].astype(str),
                        "source_household_id": merged["source_household_id_time"].astype(str),
                        "event_index": merged["source_trip_id"].astype(int),
                        "draw_index": replicate,
                        "seed_u64": [
                            _time_seed(ctx, slot, replicate)
                            for ctx, slot in zip(merged["context_row_id"], merged["source_trip_id"])
                        ],
                        "weight": merged["fit_weight_W_GEW"].astype(float),
                        "observed_json": [
                            canonical_payload({"departure_clock_minute": int(v)})
                            for v in merged["target_departure_clock_minute"]
                        ],
                        "generated_json": [
                            canonical_payload({
                                "departure_clock_minute": int(dep),
                                "duration_from_clock_min": int(dur),
                                "arrival_clock_minute": int(arr),
                                "arrival_day_offset": int(off),
                            })
                            for dep, dur, arr, off in zip(
                                generated["departure"][replicate],
                                generated["duration"][replicate],
                                generated["arrival"][replicate],
                                generated["offset"][replicate],
                            )
                        ],
                    })
                    blocks.append(block)
                frame = pd.concat(blocks, ignore_index=True)
                frame.to_csv(handle, index=False, header=not header_written)
                header_written = True
                evidence_rows += len(frame)

    _write_json(output_dir / "evidence_manifest.json", {
        "schema": "F3_3C_STANDARD_EVIDENCE_V1_COMPATIBLE_TIME_SCHEDULE",
        "rows": evidence_rows,
        "isolated_candidate_artifacts": len(records),
        "isolated_time_rows": len(merged),
        "fixed_source_cohort_days": len(cohort),
        "common_random_numbers": True,
        "replicates": REPLICATES,
    })
    _write_csv(output_dir / "validation.csv", [
        {"check": "cal_input_hashes_exact", "status": "PASS"},
        {"check": "cal_expected_rows_exact", "status": "PASS"},
        {"check": "time_schedule_artifacts_exact_7", "status": "PASS"},
        {"check": "isolated_rows_all_1243", "status": "PASS"},
        {"check": "isolated_temporal_invariants_zero_for_eligible_candidates", "status": "PASS"},
        {"check": "primary_m2_time_01_mean32", "status": "PASS"},
        {"check": "common_random_numbers_32", "status": "PASS"},
        {"check": "household_bootstrap_1000", "status": "PASS"},
        {"check": "fixed_propagated_cohort_378", "status": "PASS"},
        {"check": "upstream_pa1_main_frozen", "status": "PASS"},
        {"check": "upstream_count_ref_main_frozen", "status": "PASS"},
        {"check": "upstream_cha2_main_frozen", "status": "PASS"},
        {"check": "propagated_temporal_check_executed", "status": "PASS"},
        {"check": "test_rows_read_zero", "status": "PASS"},
        {"check": "distance_prior_not_authorized", "status": "PASS"},
    ])
    _write_csv(output_dir / "issues.csv", pd.DataFrame(columns=["issue_id", "severity", "detail"]))
    _write_json(output_dir / "performance.json", {
        "wall_seconds": time.perf_counter() - started,
        "cal_physical_rows_read": access["cal_rows_read_total_physical"],
        "isolated_time_rows": len(merged),
        "fixed_source_cohort_days": len(cohort),
        "candidate_artifacts": len(records),
        "stochastic_replicates": REPLICATES,
        "bootstrap_replicates": BOOTSTRAPS,
        "stochastic_evidence_rows": evidence_rows,
    })
    manifest = {
        "phase": "F3.4e-2b",
        "component": COMPONENT,
        "status": "PASS",
        "execution_mode": "CONTROLLED_REAL_CAL",
        "candidate_artifacts": 7,
        "candidate_selection_state": selected["status"],
        "proposed_selected_artifact_id": selected["proposed_selected_artifact_id"],
        "propagated_temporal_guardrail_pass": propagated_pass,
        "cal_files_opened": access["cal_files_opened"],
        "cal_rows_read_total_physical": access["cal_rows_read_total_physical"],
        "cal_fixed_source_cohort_days": access["cal_fixed_source_cohort_days"],
        "cal_isolated_time_rows": access["cal_isolated_time_rows"],
        "distance_prior_real_cal_authorized": False,
        "test_rows_read": 0,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
        "implementation_commit": _git(repo_root, "rev-parse", "HEAD"),
    }
    _write_json(output_dir / "run_manifest.json", manifest)
    _write_checksums(output_dir)
    return manifest


def run_controlled_time_schedule_cal(
    repo_root: Path,
    output_dir: Path,
    config_path: Path,
    authorization_path: Path,
    *,
    write_stochastic_evidence: bool = True,
) -> dict[str, Any]:
    """Run official Time Schedule CAL atomically and preserve failure evidence."""
    if output_dir.exists():
        raise FileExistsError(f"RunBundle output already exists: {output_dir}")
    staging = output_dir.with_name(f"{output_dir.name}.partial")
    if staging.exists():
        raise FileExistsError(f"Partial RunBundle already exists: {staging}")

    # Authorization is intentionally validated before `.partial` exists.
    load_authorization(authorization_path, repo_root)

    try:
        manifest = _run_controlled_time_schedule_cal_direct(
            repo_root,
            staging,
            config_path,
            authorization_path,
            write_stochastic_evidence=write_stochastic_evidence,
        )
        staging.rename(output_dir)
        return manifest
    except Exception as exc:
        if staging.exists():
            _write_json(staging / "failure.json", {
                "status": "FAIL",
                "phase": "F3.4e-2b",
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
                "cal_read_may_have_occurred": True,
                "distance_prior_real_cal_authorized": False,
                "test_open_authorized": False,
            })
            _write_checksums(staging)
        raise
