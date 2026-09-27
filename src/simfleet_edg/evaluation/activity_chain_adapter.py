"""Frozen-artifact activity-chain transition adapter. No CAL I/O occurs here."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.special import softmax

from simfleet_edg.demand.activity_chain import transform_chain_b_context
from simfleet_edg.evaluation.cal_adapter_common import ArtifactRecord, canonical_category, load_json


class ActivityChainAdapter:
    def __init__(self, repo_root: Path, record: ArtifactRecord):
        if record.component != "DG_ACTIVITY_CHAIN":
            raise ValueError("ActivityChainAdapter requires DG_ACTIVITY_CHAIN")
        self.record = record
        self.run_dir = record.validate(repo_root)
        self.model = load_json(self.run_dir / record.model_relpath)
        self.encoder = (
            load_json(self.run_dir / "chain_b_encoder_manifest.json")
            if record.candidate_id == "CHAIN_B"
            else None
        )
        self.support = list(self.model.get("activity_support", self.model.get("target_classes", [])))
        if not self.support:
            raise ValueError("Activity support is missing")

    def initial_activity_pmf(self) -> tuple[list[str], np.ndarray]:
        initial = self.model["initial_activity_model"]
        return list(initial["support"]), np.asarray(initial["probabilities"], dtype=float)

    def sample_initial_activity(self, *, seed: int) -> str:
        support, pmf = self.initial_activity_pmf()
        return str(np.random.default_rng(seed).choice(np.asarray(support, dtype=object), p=pmf))

    def _reference_pmf(self, state: dict[str, Any]) -> np.ndarray:
        previous = canonical_category(state["prefix_last_activity"])
        for cell in self.model["cells"]:
            if str(cell["previous_activity"]) == previous:
                return np.asarray(cell["probabilities"], dtype=float)
        return np.asarray(self.model["global_fallback_probabilities"], dtype=float)

    @staticmethod
    def _chain_a_cell_key(cell: dict[str, Any]) -> tuple[str, ...]:
        return tuple(str(item["value"]) for item in cell["key"])

    def _chain_a_pmf(self, state: dict[str, Any]) -> np.ndarray:
        for level in self.model["levels"]:
            dims = list(level["dimensions"])
            requested = ("GLOBAL",) if dims == ["GLOBAL"] else tuple(
                canonical_category(state[column]) for column in dims
            )
            for cell in level["cells"]:
                if self._chain_a_cell_key(cell) == requested and bool(cell["eligible_direct"]):
                    return np.asarray(cell["probabilities"], dtype=float)
        raise RuntimeError("CHAIN_A deterministic backoff failed")

    def _chain_b_pmf(self, frame: pd.DataFrame) -> np.ndarray:
        assert self.encoder is not None
        x, _ = transform_chain_b_context(frame, self.encoder)
        intercept = np.asarray(self.model["intercepts_nonreference"], dtype=float)
        beta = np.asarray(self.model["coefficients_nonreference"], dtype=float)
        logits = np.zeros((len(frame), len(self.model["target_classes"])), dtype=float)
        logits[:, 1:] = intercept[None, :] + x @ beta.T
        return softmax(logits, axis=1)

    def transition_pmf(self, frame: pd.DataFrame) -> np.ndarray:
        if self.record.candidate_id == "CHAIN_REF":
            return np.vstack([self._reference_pmf(row.to_dict()) for _, row in frame.iterrows()])
        if self.record.candidate_id == "CHAIN_A":
            return np.vstack([self._chain_a_pmf(row.to_dict()) for _, row in frame.iterrows()])
        if self.record.candidate_id == "CHAIN_B":
            return self._chain_b_pmf(frame)
        raise ValueError(f"Unsupported activity-chain candidate {self.record.candidate_id}")

    def sample_transition(self, frame: pd.DataFrame, *, seed: int) -> dict[str, Any]:
        if len(frame) != 1:
            raise ValueError("sample_transition requires exactly one row")
        pmf = self.transition_pmf(frame)[0]
        next_activity = str(
            np.random.default_rng(seed).choice(np.asarray(self.support, dtype=object), p=pmf)
        )
        return {"next_activity": next_activity, "support": self.support, "probabilities": pmf.tolist()}
