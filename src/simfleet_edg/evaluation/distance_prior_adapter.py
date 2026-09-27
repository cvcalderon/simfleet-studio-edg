"""Frozen-artifact distance-prior adapter. No CAL I/O occurs here."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

from simfleet_edg.demand.distance_prior import (
    inverse_ecdf_value,
    repair_distance_quantiles,
    sample_distance_a,
    sample_distance_b,
    transform_distance_b_context,
)
from simfleet_edg.evaluation.cal_adapter_common import ArtifactRecord, load_json


class DistancePriorAdapter:
    def __init__(self, repo_root: Path, record: ArtifactRecord):
        if record.component != "DG_DISTANCE_PRIOR":
            raise ValueError("DistancePriorAdapter requires DG_DISTANCE_PRIOR")
        self.record = record
        self.run_dir = record.validate(repo_root)
        self.model = load_json(self.run_dir / record.model_relpath)
        self.encoder = (
            load_json(self.run_dir / "distance_b_encoder_manifest.json")
            if record.candidate_id == "DIST_B"
            else None
        )
        self.quantiles = [float(q) for q in self.model.get("quantiles", [])]
        self.boosters: dict[str, lgb.Booster] = {}
        if record.candidate_id == "DIST_B":
            self.boosters = {
                key: lgb.Booster(model_str=spec["booster_model_string"])
                for key, spec in self.model["boosters"].items()
            }

    def _sample_ref(self, *, seed: int) -> dict[str, Any]:
        u = float(np.random.default_rng(seed).random())
        return {
            "distance_prior_km": inverse_ecdf_value(self.model["support"], u),
            "draw_uniform": u,
            "selected_level": 0,
        }

    def _sample_b(self, frame: pd.DataFrame, *, seed: int) -> dict[str, Any]:
        assert self.encoder is not None
        x, _ = transform_distance_b_context(frame, self.encoder)
        x_frame = pd.DataFrame(x, columns=self.encoder["feature_names"])
        raw = np.column_stack([
            np.asarray(self.boosters[f"q{q:.2f}"].predict(x_frame), dtype=float)
            for q in self.quantiles
        ])
        lo = float(self.model["global_strict_train_target_min_km"])
        hi = float(self.model["global_strict_train_target_max_km"])
        repaired = repair_distance_quantiles(raw, lo, hi)
        u = float(np.random.default_rng(seed).random())
        return {
            "distance_prior_km": sample_distance_b(
                repaired[0], self.quantiles, uniform=u, target_min=lo, target_max=hi
            ),
            "draw_uniform": u,
            "selected_level": None,
        }

    def sample_one(self, frame: pd.DataFrame, *, seed: int) -> dict[str, Any]:
        if len(frame) != 1:
            raise ValueError("sample_one requires exactly one row")
        if self.record.candidate_id == "DIST_REF":
            return self._sample_ref(seed=seed)
        if self.record.candidate_id == "DIST_A":
            return sample_distance_a(self.model, frame.iloc[0].to_dict(), seed=seed)
        if self.record.candidate_id == "DIST_B":
            return self._sample_b(frame, seed=seed)
        raise ValueError(f"Unsupported distance candidate {self.record.candidate_id}")
