"""Frozen-artifact positive trip-count adapter. No CAL I/O occurs here."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from simfleet_edg.demand.trip_count import nb2_truncated_pmf_matrix, transform_count_context
from simfleet_edg.evaluation.cal_adapter_common import ArtifactRecord, canonical_category, load_json


class TripCountAdapter:
    def __init__(self, repo_root: Path, record: ArtifactRecord):
        if record.component != "DG_TRIP_COUNT":
            raise ValueError("TripCountAdapter requires DG_TRIP_COUNT")
        self.record = record
        self.run_dir = record.validate(repo_root)
        self.model = load_json(self.run_dir / record.model_relpath)
        self.encoder = (
            load_json(self.run_dir / "count_a_encoder_manifest.json")
            if record.candidate_id == "COUNT_A"
            else None
        )
        self.support = np.asarray(self.model["support_k"] if "support_k" in self.model else range(
            int(self.model["k_min"]), int(self.model["k_max_train"]) + 1
        ), dtype=int)

    @property
    def required_columns(self) -> list[str]:
        if self.encoder is not None:
            return list(self.encoder["feature_columns"])
        if self.record.candidate_id == "COUNT_B":
            columns: list[str] = []
            for level in self.model["levels"]:
                for column in level["dimensions"]:
                    if column != "GLOBAL" and column not in columns:
                        columns.append(column)
            return columns
        return []

    def _count_b_pmf(self, state: dict[str, Any]) -> np.ndarray:
        for level in self.model["levels"]:
            dimensions = list(level["dimensions"])
            requested = () if dimensions == ["GLOBAL"] else tuple(
                canonical_category(state[column]) for column in dimensions
            )
            for cell in level["cells"]:
                key = tuple(str(value) for value in cell["key"])
                if key == requested and bool(cell["eligible_direct"]):
                    return np.asarray(cell["probabilities"], dtype=float)
        raise RuntimeError("COUNT_B deterministic backoff failed")

    def pmf(self, frame: pd.DataFrame) -> np.ndarray:
        if self.record.candidate_id == "COUNT_REF":
            return np.repeat(
                np.asarray(self.model["probabilities"], dtype=float)[None, :], len(frame), axis=0
            )
        if self.record.candidate_id == "COUNT_A":
            assert self.encoder is not None
            x, _ = transform_count_context(frame, self.encoder)
            beta = np.asarray(self.model["coefficients"], dtype=float)
            mu = np.exp(float(self.model["intercept"]) + x @ beta)
            return nb2_truncated_pmf_matrix(
                mu,
                float(self.model["alpha"]),
                int(self.model["k_min"]),
                int(self.model["k_max_train"]),
            )
        if self.record.candidate_id == "COUNT_B":
            return np.vstack([self._count_b_pmf(row.to_dict()) for _, row in frame.iterrows()])
        raise ValueError(f"Unsupported trip-count candidate {self.record.candidate_id}")

    def sample_one(self, frame: pd.DataFrame, *, seed: int) -> dict[str, Any]:
        if len(frame) != 1:
            raise ValueError("sample_one requires exactly one row")
        pmf = self.pmf(frame)[0]
        if not np.isclose(pmf.sum(), 1.0, atol=1e-10):
            raise ValueError("Count PMF is not normalized")
        k = int(np.random.default_rng(seed).choice(self.support, p=pmf))
        return {"trip_count": k, "support_k": self.support.tolist(), "probabilities": pmf.tolist()}
