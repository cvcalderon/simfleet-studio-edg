"""Frozen-artifact planned-time adapter. No CAL I/O occurs here."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

from simfleet_edg.demand.time_schedule import (
    sample_time_a,
    transform_time_b_context,
    validate_temporal_row,
)
from simfleet_edg.evaluation.cal_adapter_common import ArtifactRecord, load_json


class TimeScheduleAdapter:
    MAX_REJECTION_ATTEMPTS = 100
    DEP_MIN = 0
    DEP_MAX = 1439
    DUR_MIN = 1
    DUR_MAX = 480

    def __init__(self, repo_root: Path, record: ArtifactRecord):
        if record.component != "DG_TIME_SCHEDULE":
            raise ValueError("TimeScheduleAdapter requires DG_TIME_SCHEDULE")
        self.record = record
        self.run_dir = record.validate(repo_root)
        self.model = load_json(self.run_dir / record.model_relpath)
        self.encoder = (
            load_json(self.run_dir / "time_b_encoder_manifest.json")
            if record.candidate_id == "TIME_B"
            else None
        )
        self.quantiles = [float(q) for q in self.model.get("quantiles", [])]
        self.boosters: dict[str, dict[str, lgb.Booster]] = {}
        if record.candidate_id == "TIME_B":
            for target, quantile_models in self.model["boosters"].items():
                self.boosters[target] = {
                    key: lgb.Booster(model_str=spec["booster_model_string"])
                    for key, spec in quantile_models.items()
                }

    @staticmethod
    def _round_half_up(value: float) -> int:
        return int(math.floor(float(value) + 0.5))

    def _sample_reference(
        self,
        *,
        previous_arrival_absolute_minute: float | None,
        trips_remaining_after_current: int,
        seed: int,
    ) -> dict[str, Any]:
        rng = np.random.default_rng(seed)
        support = list(self.model["joint_temporal_support"])
        p = np.asarray([float(row["probability"]) for row in support], dtype=float)
        for attempt in range(1, self.MAX_REJECTION_ATTEMPTS + 1):
            sample = support[int(rng.choice(len(support), p=p))]
            ok, result = validate_temporal_row(
                int(sample["departure_clock_minute"]),
                int(sample["duration_from_clock_min"]),
                previous_arrival_absolute_minute=previous_arrival_absolute_minute,
                trips_remaining_after_current=trips_remaining_after_current,
            )
            if ok:
                return {**result, "attempt": attempt, "selected_level": 0}
        raise RuntimeError("TIME_REF exhausted 100 rejection attempts")

    def _time_b_quantiles(self, frame: pd.DataFrame) -> dict[str, np.ndarray]:
        assert self.encoder is not None
        x, _ = transform_time_b_context(frame, self.encoder)
        x_frame = pd.DataFrame(x, columns=self.encoder["feature_names"])
        output: dict[str, np.ndarray] = {}
        bounds = {
            "departure_clock_minute": (self.DEP_MIN, self.DEP_MAX),
            "duration_from_clock_min": (self.DUR_MIN, self.DUR_MAX),
        }
        for target, boosters in self.boosters.items():
            raw = np.column_stack([
                np.asarray(boosters[f"q{q:.2f}"].predict(x_frame), dtype=float)
                for q in self.quantiles
            ])
            lo, hi = bounds[target]
            output[target] = np.maximum.accumulate(np.clip(raw, lo, hi), axis=1)
        return output

    def _sample_time_b(
        self,
        frame: pd.DataFrame,
        *,
        previous_arrival_absolute_minute: float | None,
        trips_remaining_after_current: int,
        seed: int,
    ) -> dict[str, Any]:
        if len(frame) != 1:
            raise ValueError("TIME_B sample requires one state row")
        repaired = self._time_b_quantiles(frame)
        dep_knots = repaired["departure_clock_minute"][0]
        dur_knots = repaired["duration_from_clock_min"][0]
        xp = np.asarray([0.0, *self.quantiles, 1.0], dtype=float)
        dep_fp = np.asarray([self.DEP_MIN, *dep_knots.tolist(), self.DEP_MAX], dtype=float)
        dur_fp = np.asarray([self.DUR_MIN, *dur_knots.tolist(), self.DUR_MAX], dtype=float)
        if np.any(np.diff(dep_fp) < -1e-12) or np.any(np.diff(dur_fp) < -1e-12):
            raise ValueError("TIME_B reconstruction knots are not monotone")
        rng = np.random.default_rng(seed)
        for attempt in range(1, self.MAX_REJECTION_ATTEMPTS + 1):
            u_dep = float(rng.random())
            u_dur = float(rng.random())
            departure = self._round_half_up(np.interp(u_dep, xp, dep_fp))
            duration = self._round_half_up(np.interp(u_dur, xp, dur_fp))
            departure = min(max(departure, self.DEP_MIN), self.DEP_MAX)
            duration = min(max(duration, self.DUR_MIN), self.DUR_MAX)
            ok, result = validate_temporal_row(
                departure,
                duration,
                previous_arrival_absolute_minute=previous_arrival_absolute_minute,
                trips_remaining_after_current=trips_remaining_after_current,
            )
            if ok:
                return {
                    **result,
                    "attempt": attempt,
                    "uniform_departure": u_dep,
                    "uniform_duration": u_dur,
                    "selected_level": None,
                }
        raise RuntimeError("TIME_B exhausted 100 rejection attempts")

    def sample_one(
        self,
        frame: pd.DataFrame,
        *,
        previous_arrival_absolute_minute: float | None,
        trips_remaining_after_current: int,
        seed: int,
    ) -> dict[str, Any]:
        if len(frame) != 1:
            raise ValueError("sample_one requires exactly one row")
        if self.record.candidate_id == "TIME_REF":
            return self._sample_reference(
                previous_arrival_absolute_minute=previous_arrival_absolute_minute,
                trips_remaining_after_current=trips_remaining_after_current,
                seed=seed,
            )
        if self.record.candidate_id == "TIME_A":
            return sample_time_a(
                self.model,
                frame.iloc[0].to_dict(),
                previous_arrival_absolute_minute=previous_arrival_absolute_minute,
                trips_remaining_after_current=trips_remaining_after_current,
                seed=seed,
            )
        if self.record.candidate_id == "TIME_B":
            return self._sample_time_b(
                frame,
                previous_arrival_absolute_minute=previous_arrival_absolute_minute,
                trips_remaining_after_current=trips_remaining_after_current,
                seed=seed,
            )
        raise ValueError(f"Unsupported time candidate {self.record.candidate_id}")
