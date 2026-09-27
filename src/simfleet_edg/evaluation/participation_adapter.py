"""Frozen-artifact participation adapter. No CAL I/O occurs here."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.special import expit

from simfleet_edg.demand.participation import transform_context
from simfleet_edg.evaluation.cal_adapter_common import ArtifactRecord, load_json


class ParticipationAdapter:
    def __init__(self, repo_root: Path, record: ArtifactRecord):
        if record.component != "DG_PARTICIPATION":
            raise ValueError("ParticipationAdapter requires DG_PARTICIPATION")
        self.record = record
        self.run_dir = record.validate(repo_root)
        self.model_path = self.run_dir / record.model_relpath
        self.encoder = load_json(self.run_dir / "encoder_manifest.json")
        self.model: dict[str, Any] | None = None
        self.booster: lgb.Booster | None = None
        if record.candidate_id == "PART_B":
            self.booster = lgb.Booster(model_file=str(self.model_path))
        else:
            self.model = load_json(self.model_path)

    @property
    def required_columns(self) -> list[str]:
        return list(self.encoder["feature_columns"])

    def probabilities(self, frame: pd.DataFrame) -> np.ndarray:
        if self.record.candidate_id == "PART_REF":
            assert self.model is not None
            p = np.full(len(frame), float(self.model["probability_trip_day"]), dtype=float)
        else:
            x, _ = transform_context(frame, self.encoder)
            if self.record.candidate_id == "PART_A":
                assert self.model is not None
                beta = np.asarray(self.model["coefficients"], dtype=float)
                p = expit(float(self.model["intercept"]) + x @ beta)
            elif self.record.candidate_id == "PART_B":
                assert self.booster is not None
                x_frame = pd.DataFrame(x, columns=self.encoder["feature_names"])
                p = np.asarray(self.booster.predict(x_frame), dtype=float)
            else:
                raise ValueError(f"Unsupported participation candidate {self.record.candidate_id}")
        if not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
            raise ValueError("Participation adapter produced invalid probabilities")
        return p

    def sample_one(self, frame: pd.DataFrame, *, seed: int) -> dict[str, Any]:
        if len(frame) != 1:
            raise ValueError("sample_one requires exactly one row")
        p = float(self.probabilities(frame)[0])
        draw = bool(np.random.default_rng(seed).random() < p)
        return {"probability_trip_day": p, "trip_day": draw}
