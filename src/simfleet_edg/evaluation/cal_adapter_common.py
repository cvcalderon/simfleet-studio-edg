"""Shared artifact-loading and draw-identity utilities for F3.3b CAL adapters."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from simfleet_edg.evaluation.cal_protocol import CAL_SCENARIO_ID, MASTER_SEED, runtime_draw_seed

MISSING = "__MISSING_CONTEXT__"
UNSEEN = "__UNSEEN__"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_category(value: Any) -> str:
    if pd.isna(value):
        return MISSING
    if isinstance(value, (np.integer, int)):
        return str(int(value))
    if isinstance(value, (np.floating, float)) and float(value).is_integer():
        return str(int(value))
    return str(value)


@dataclass(frozen=True)
class ArtifactRecord:
    component: str
    candidate_id: str
    grid_id: str
    role: str
    artifact_id: str
    official_run_dir: str
    model_relpath: str
    artifact_manifest_relpath: str
    model_sha256: str
    manifest_sha256: str
    train_state: str

    @classmethod
    def from_series(cls, row: pd.Series) -> ArtifactRecord:
        return cls(**{name: str(row[name]) for name in cls.__dataclass_fields__})

    def validate(self, repo_root: Path) -> Path:
        if self.train_state != "FITTED_TRAIN_ONLY_NOT_SELECTED":
            raise ValueError(f"Unexpected TRAIN state for {self.artifact_id}: {self.train_state}")
        run_dir = repo_root / "artifacts" / "runs" / self.official_run_dir
        model = run_dir / self.model_relpath
        manifest = run_dir / self.artifact_manifest_relpath
        if not model.is_file() or not manifest.is_file():
            raise FileNotFoundError(f"Missing frozen artifact bytes for {self.artifact_id}")
        if sha256_file(model) != self.model_sha256:
            raise ValueError(f"Model SHA mismatch for {self.artifact_id}")
        if sha256_file(manifest) != self.manifest_sha256:
            raise ValueError(f"Manifest SHA mismatch for {self.artifact_id}")
        return run_dir


def load_registry(path: Path) -> list[ArtifactRecord]:
    frame = pd.read_csv(path, dtype=str)
    records = [ArtifactRecord.from_series(row) for _, row in frame.iterrows()]
    if len(records) != 31:
        raise ValueError(f"Expected 31 frozen artifacts, got {len(records)}")
    ids = [record.artifact_id for record in records]
    if len(set(ids)) != len(ids):
        raise ValueError("Artifact ids must be unique")
    return records


@dataclass(frozen=True)
class AdapterDrawIdentity:
    generated_person_id: str
    draw_index: int
    scenario_id: str = CAL_SCENARIO_ID
    master_seed: int = MASTER_SEED

    def seed(self, component: str) -> int:
        if self.draw_index < 0:
            raise ValueError("draw_index must be non-negative")
        return runtime_draw_seed(
            self.master_seed,
            self.scenario_id,
            self.generated_person_id,
            component,
            self.draw_index,
        )


def choice_from_pmf(support: list[Any], probabilities: np.ndarray, *, seed: int) -> Any:
    p = np.asarray(probabilities, dtype=float)
    if p.ndim != 1 or len(p) != len(support):
        raise ValueError("support/PMF mismatch")
    if not np.isfinite(p).all() or (p < 0).any() or not np.isclose(p.sum(), 1.0, atol=1e-10):
        raise ValueError("invalid PMF")
    rng = np.random.default_rng(seed)
    return rng.choice(np.asarray(support, dtype=object), p=p).item()
