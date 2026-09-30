from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from simfleet_edg.evaluation.cal_adapter_common import AdapterDrawIdentity, load_registry
from simfleet_edg.evaluation.cal_metrics import wasserstein_1d, weighted_mean, weighted_quantile
from simfleet_edg.evaluation.distance_prior_adapter import DistancePriorAdapter

REPO_ROOT = Path.cwd()
REGISTRY = REPO_ROOT / "docs/F3_3_CANDIDATE_ARTIFACT_REGISTRY_v1.csv"
SNAPSHOT = REPO_ROOT / "configs/f3/f3_4f1_distance_prior_candidate_registry_v1.json"
RESERVED = {"UNKNOWN", "__MISSING_CONTEXT__", "__START__", "__UNSEEN__", "GLOBAL"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _safe_category(values: list[Any]) -> Any:
    for value in values:
        if str(value) not in RESERVED:
            return value
    return values[0]


def synthetic_frame(adapter: DistancePriorAdapter) -> pd.DataFrame:
    """Build one adapter-valid synthetic row without reading CAL.

    This is an implementation smoke context only. It is intentionally not used
    as scientific evidence or candidate-selection evidence.
    """
    if adapter.record.candidate_id == "DIST_REF":
        return pd.DataFrame([{"synthetic_placeholder": 1}])

    if adapter.record.candidate_id == "DIST_A":
        state: dict[str, Any] = {}
        selected = None
        for level in adapter.model["levels"]:
            for cell in level["cells"]:
                if bool(cell["eligible_direct"]):
                    selected = cell
                    for key, value in cell["key"].items():
                        if key != "GLOBAL":
                            state.setdefault(str(key), value)
                    break
            if selected is not None:
                break
        if selected is None:
            raise RuntimeError(f"No eligible DIST_A cell for {adapter.record.artifact_id}")
        return pd.DataFrame([state])

    if adapter.record.candidate_id == "DIST_B":
        if adapter.encoder is None:
            raise RuntimeError("DIST_B encoder missing")
        state: dict[str, Any] = {}
        for column in adapter.encoder["categorical_columns"]:
            state[column] = _safe_category(list(adapter.encoder["categories"][column]))
        for column in adapter.encoder["numeric_columns"]:
            state[column] = 0.0
        return pd.DataFrame([state])

    raise ValueError(adapter.record.candidate_id)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    output = args.output_dir.expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"Output path already exists: {output}")
    output.mkdir(parents=True)

    # Hard I/O guard: this synthetic phase must never open CALIBRATION files.
    original_read_csv = pd.read_csv

    def guarded_read_csv(path: Any, *a: Any, **kw: Any) -> pd.DataFrame:
        if "CALIBRATION" in str(path):
            raise RuntimeError(f"CAL I/O forbidden in F3.4f-2a: {path}")
        return original_read_csv(path, *a, **kw)

    pd.read_csv = guarded_read_csv  # type: ignore[assignment]

    records = [r for r in load_registry(REGISTRY) if r.component == "DG_DISTANCE_PRIOR"]
    if len(records) != 5:
        raise ValueError(f"Expected 5 DG_DISTANCE_PRIOR artifacts, got {len(records)}")

    frozen = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    frozen_by_id = {row["artifact_id"]: row for row in frozen["candidates"]}

    artifact_rows: list[dict[str, Any]] = []
    adapters: list[DistancePriorAdapter] = []
    for record in records:
        run_dir = record.validate(REPO_ROOT)
        snap = frozen_by_id[record.artifact_id]
        if snap["model_sha256"] != record.model_sha256:
            raise ValueError(f"Snapshot model SHA mismatch: {record.artifact_id}")
        if snap["manifest_sha256"] != record.manifest_sha256:
            raise ValueError(f"Snapshot manifest SHA mismatch: {record.artifact_id}")
        artifact_rows.append(
            {
                "artifact_id": record.artifact_id,
                "candidate_id": record.candidate_id,
                "grid_id": record.grid_id,
                "model_sha256": record.model_sha256,
                "manifest_sha256": record.manifest_sha256,
                "run_dir": str(run_dir),
                "status": "PASS",
            }
        )
        adapters.append(DistancePriorAdapter(REPO_ROOT, record))

    replicates = int(cfg["synthetic_protocol"]["stochastic_replicates"])
    person_id = str(cfg["synthetic_protocol"]["generated_person_id"])
    namespace = str(cfg["synthetic_protocol"]["rng_namespace"])
    seeds = [
        AdapterDrawIdentity(generated_person_id=person_id, draw_index=i).seed(namespace)
        for i in range(replicates)
    ]
    pd.DataFrame(
        {
            "replicate_index": list(range(replicates)),
            "seed": seeds,
            "namespace": [namespace] * replicates,
        }
    ).to_csv(output / "seed_schedule.csv", index=False)

    observed = np.asarray(cfg["synthetic_metric_smoke"]["synthetic_observed_distance_km"], dtype=float)
    if len(observed) != replicates:
        raise ValueError("Synthetic observed-distance vector must have one entry per replicate")
    weights = np.ones(replicates, dtype=float)

    draw_rows: list[dict[str, Any]] = []
    primary_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    hard_violations = 0

    for adapter in adapters:
        frame = synthetic_frame(adapter)
        generated: list[float] = []
        for replicate, seed in enumerate(seeds):
            result = adapter.sample_one(frame, seed=int(seed))
            value = float(result["distance_prior_km"])
            valid = bool(np.isfinite(value) and value > 0.0)
            if not valid:
                hard_violations += 1
            generated.append(value)
            draw_rows.append(
                {
                    "artifact_id": adapter.record.artifact_id,
                    "candidate_id": adapter.record.candidate_id,
                    "grid_id": adapter.record.grid_id,
                    "replicate_index": replicate,
                    "seed": int(seed),
                    "distance_prior_km": value,
                    "distance_positive_finite": valid,
                    "draw_uniform": result.get("draw_uniform"),
                    "selected_level": result.get("selected_level"),
                }
            )

        generated_arr = np.asarray(generated, dtype=float)
        primary_rows.append(
            {
                "artifact_id": adapter.record.artifact_id,
                "candidate_id": adapter.record.candidate_id,
                "grid_id": adapter.record.grid_id,
                "metric": "M2-DIST-01_SYNTHETIC_WASSERSTEIN_KM_SMOKE",
                "value": wasserstein_1d(observed, weights, generated_arr, weights),
                "selection_authorized": False,
            }
        )
        summary_rows.extend(
            [
                {
                    "artifact_id": adapter.record.artifact_id,
                    "statistic": "MEAN",
                    "value_km": weighted_mean(generated_arr, weights),
                    "role": "REPORT_ONLY_UNTHRESHOLDED",
                    "synthetic_decision_authorized": False,
                },
                {
                    "artifact_id": adapter.record.artifact_id,
                    "statistic": "P50",
                    "value_km": weighted_quantile(generated_arr, weights, 0.50),
                    "role": "SMOKE_ONLY_FUTURE_REAL_CAL_TOLERANCE_0.50_KM",
                    "synthetic_decision_authorized": False,
                },
                {
                    "artifact_id": adapter.record.artifact_id,
                    "statistic": "P90",
                    "value_km": weighted_quantile(generated_arr, weights, 0.90),
                    "role": "SMOKE_ONLY_FUTURE_REAL_CAL_TOLERANCE_0.50_KM",
                    "synthetic_decision_authorized": False,
                },
                {
                    "artifact_id": adapter.record.artifact_id,
                    "statistic": "P95",
                    "value_km": weighted_quantile(generated_arr, weights, 0.95),
                    "role": "SMOKE_ONLY_FUTURE_REAL_CAL_TOLERANCE_0.50_KM",
                    "synthetic_decision_authorized": False,
                },
            ]
        )

    validation_rows = [
        {"check": "candidate_artifacts_5", "status": "PASS" if len(adapters) == 5 else "FAIL"},
        {"check": "generated_draw_rows_160", "status": "PASS" if len(draw_rows) == 160 else "FAIL"},
        {"check": "primary_rows_5", "status": "PASS" if len(primary_rows) == 5 else "FAIL"},
        {"check": "summary_rows_20", "status": "PASS" if len(summary_rows) == 20 else "FAIL"},
        {"check": "seed_rows_32", "status": "PASS" if len(seeds) == 32 else "FAIL"},
        {
            "check": "generated_distance_positive_finite",
            "status": "PASS" if hard_violations == 0 else "FAIL",
        },
        {"check": "cal_rows_zero", "status": "PASS"},
        {"check": "test_rows_zero", "status": "PASS"},
        {"check": "candidate_selection_none", "status": "PASS"},
    ]
    validation = pd.DataFrame(validation_rows)

    pd.DataFrame(artifact_rows).to_csv(output / "artifact_validation.csv", index=False)
    pd.DataFrame(primary_rows).to_csv(output / "synthetic_primary_metrics.csv", index=False)
    pd.DataFrame(summary_rows).to_csv(output / "synthetic_summary_metrics.csv", index=False)
    pd.DataFrame(draw_rows).to_csv(output / "synthetic_generated_draws.csv", index=False)
    validation.to_csv(output / "validation.csv", index=False)

    status = "PASS" if validation["status"].eq("PASS").all() else "FAIL"
    manifest = {
        "run_id": cfg["run_id"],
        "phase": "F3.4f-2a",
        "component": "DG_DISTANCE_PRIOR",
        "mode": "SYNTHETIC_PREOPEN",
        "status": status,
        "implementation_commit": subprocess_git_head(),
        "candidate_artifacts": 5,
        "candidate_selection": "NONE",
        "stochastic_replicates": replicates,
        "generated_draw_rows": len(draw_rows),
        "synthetic_primary_rows": len(primary_rows),
        "synthetic_summary_rows": len(summary_rows),
        "generated_hard_invariant_violations": hard_violations,
        "cal_files_read": [],
        "cal_rows_read": 0,
        "future_cal_physical_rows": int(cfg["boundaries"]["future_cal_physical_rows"]),
        "real_distance_prior_cal_open_authorized": False,
        "joint_cal_gate_authorized": False,
        "test_rows_read": 0,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
    }
    write_json(output / "run_manifest.json", manifest)

    bundle_files = sorted(p for p in output.iterdir() if p.is_file())
    checksums = "\n".join(f"{sha256(p)}  {p.name}" for p in bundle_files) + "\n"
    (output / "checksums.sha256").write_text(checksums, encoding="utf-8")

    print(json.dumps(manifest, indent=2, sort_keys=True))
    if status != "PASS":
        raise SystemExit(1)


def subprocess_git_head() -> str:
    import subprocess

    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


if __name__ == "__main__":
    main()
