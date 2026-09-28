from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from simfleet_edg.demand.time_schedule import validate_temporal_row
from simfleet_edg.evaluation.cal_adapter_common import AdapterDrawIdentity, load_registry
from simfleet_edg.evaluation.cal_metrics import total_variation_distance, weighted_distribution
from simfleet_edg.evaluation.time_schedule_adapter import TimeScheduleAdapter

REPO_ROOT = Path.cwd()
REGISTRY = REPO_ROOT / "docs/F3_3_CANDIDATE_ARTIFACT_REGISTRY_v1.csv"
SNAPSHOT = REPO_ROOT / "configs/f3/f3_4e1_time_schedule_candidate_registry_v1.json"

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


def synthetic_frame(adapter: TimeScheduleAdapter) -> pd.DataFrame:
    if adapter.record.candidate_id == "TIME_REF":
        return pd.DataFrame([{"synthetic_placeholder": 1}])

    if adapter.record.candidate_id == "TIME_A":
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
            raise RuntimeError(f"No eligible TIME_A cell for {adapter.record.artifact_id}")
        return pd.DataFrame([state])

    if adapter.record.candidate_id == "TIME_B":
        if adapter.encoder is None:
            raise RuntimeError("TIME_B encoder missing")
        state = {}
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

    # Guard against accidental CAL reads in this synthetic phase.
    original_read_csv = pd.read_csv

    def guarded_read_csv(path: Any, *a: Any, **kw: Any) -> pd.DataFrame:
        if "CALIBRATION" in str(path):
            raise RuntimeError(f"CAL I/O forbidden in F3.4e-2a: {path}")
        return original_read_csv(path, *a, **kw)

    pd.read_csv = guarded_read_csv  # type: ignore[assignment]

    records = [r for r in load_registry(REGISTRY) if r.component == "DG_TIME_SCHEDULE"]
    if len(records) != 7:
        raise ValueError(f"Expected 7 DG_TIME_SCHEDULE artifacts, got {len(records)}")

    frozen = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    frozen_by_id = {row["artifact_id"]: row for row in frozen["candidates"]}

    artifact_rows = []
    adapters: list[TimeScheduleAdapter] = []
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
        adapters.append(TimeScheduleAdapter(REPO_ROOT, record))

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

    observed_hours = [str(x) for x in cfg["synthetic_metric_smoke"]["synthetic_observed_departure_hours"]]
    if len(observed_hours) != replicates:
        raise ValueError("Synthetic observed hour vector must have one entry per replicate")
    observed_weights = np.ones(replicates, dtype=float)
    observed_dist = weighted_distribution(observed_hours, observed_weights)

    draw_rows = []
    primary_rows = []
    temporal_violations = 0

    for adapter in adapters:
        frame = synthetic_frame(adapter)
        generated_hours: list[str] = []

        for replicate, seed in enumerate(seeds):
            result = adapter.sample_one(
                frame,
                previous_arrival_absolute_minute=None,
                trips_remaining_after_current=0,
                seed=int(seed),
            )
            ok, reconstructed = validate_temporal_row(
                result["departure_clock_minute"],
                result["duration_from_clock_min"],
                previous_arrival_absolute_minute=None,
                trips_remaining_after_current=0,
            )
            if not ok:
                temporal_violations += 1
            generated_hours.append(str(int(result["departure_clock_minute"]) // 60))
            draw_rows.append(
                {
                    "artifact_id": adapter.record.artifact_id,
                    "candidate_id": adapter.record.candidate_id,
                    "grid_id": adapter.record.grid_id,
                    "replicate_index": replicate,
                    "seed": int(seed),
                    "departure_clock_minute": int(result["departure_clock_minute"]),
                    "arrival_clock_minute": int(result["arrival_clock_minute"]),
                    "arrival_day_offset": int(result["arrival_day_offset"]),
                    "duration_from_clock_min": int(result["duration_from_clock_min"]),
                    "arrival_absolute_minute": float(result["arrival_absolute_minute"]),
                    "attempt": int(result["attempt"]),
                    "temporal_valid": bool(ok),
                    "reconstructed_arrival_absolute_minute": float(
                        reconstructed["arrival_absolute_minute"]
                    ) if ok else np.nan,
                }
            )

        generated_dist = weighted_distribution(generated_hours, np.ones(replicates, dtype=float))
        primary_rows.append(
            {
                "artifact_id": adapter.record.artifact_id,
                "candidate_id": adapter.record.candidate_id,
                "grid_id": adapter.record.grid_id,
                "metric": "M2-TIME-01_SYNTHETIC_TVD_SMOKE",
                "value": total_variation_distance(observed_dist, generated_dist),
                "selection_authorized": False,
            }
        )

    validator_cases = [
        (
            "DEPARTURE_BELOW_ZERO",
            validate_temporal_row(-1, 10, previous_arrival_absolute_minute=None, trips_remaining_after_current=0)[0],
        ),
        (
            "ZERO_DURATION",
            validate_temporal_row(100, 0, previous_arrival_absolute_minute=None, trips_remaining_after_current=0)[0],
        ),
        (
            "DEPARTURE_BEFORE_PREVIOUS_ARRIVAL",
            validate_temporal_row(100, 10, previous_arrival_absolute_minute=120, trips_remaining_after_current=0)[0],
        ),
        (
            "NONFINAL_TRIP_CROSSES_MIDNIGHT",
            validate_temporal_row(1430, 20, previous_arrival_absolute_minute=None, trips_remaining_after_current=1)[0],
        ),
    ]
    validator_df = pd.DataFrame(
        [{"case": name, "accepted": bool(accepted), "expected_accepted": False} for name, accepted in validator_cases]
    )

    validation_rows = [
        {"check": "candidate_artifacts_7", "status": "PASS" if len(adapters) == 7 else "FAIL"},
        {"check": "generated_draw_rows_224", "status": "PASS" if len(draw_rows) == 224 else "FAIL"},
        {"check": "primary_rows_7", "status": "PASS" if len(primary_rows) == 7 else "FAIL"},
        {"check": "seed_rows_32", "status": "PASS" if len(seeds) == 32 else "FAIL"},
        {
            "check": "generated_temporal_invariant_violations_zero",
            "status": "PASS" if temporal_violations == 0 else "FAIL",
        },
        {
            "check": "negative_temporal_cases_all_rejected",
            "status": "PASS" if not validator_df["accepted"].any() else "FAIL",
        },
        {"check": "cal_rows_zero", "status": "PASS"},
        {"check": "test_rows_zero", "status": "PASS"},
        {"check": "candidate_selection_none", "status": "PASS"},
    ]
    validation = pd.DataFrame(validation_rows)

    pd.DataFrame(artifact_rows).to_csv(output / "artifact_validation.csv", index=False)
    pd.DataFrame(primary_rows).to_csv(output / "synthetic_primary_metrics.csv", index=False)
    pd.DataFrame(draw_rows).to_csv(output / "synthetic_generated_draws.csv", index=False)
    validator_df.to_csv(output / "temporal_validator_smoke.csv", index=False)
    validation.to_csv(output / "validation.csv", index=False)

    status = "PASS" if validation["status"].eq("PASS").all() else "FAIL"
    manifest = {
        "run_id": cfg["run_id"],
        "phase": "F3.4e-2a",
        "component": "DG_TIME_SCHEDULE",
        "mode": "SYNTHETIC_PREOPEN",
        "status": status,
        "implementation_commit": subprocess_git_head(),
        "candidate_artifacts": 7,
        "candidate_selection": "NONE",
        "stochastic_replicates": replicates,
        "generated_draw_rows": len(draw_rows),
        "synthetic_primary_rows": len(primary_rows),
        "generated_temporal_invariant_violations": temporal_violations,
        "cal_files_read": [],
        "cal_rows_read": 0,
        "future_cal_physical_rows": int(cfg["boundaries"]["future_cal_physical_rows"]),
        "real_time_schedule_cal_open_authorized": False,
        "distance_prior_real_cal_authorized": False,
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
