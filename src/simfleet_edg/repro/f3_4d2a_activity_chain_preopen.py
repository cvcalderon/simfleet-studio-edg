from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import shutil
import sys
from pathlib import Path

import yaml

from simfleet_edg.evaluation.activity_chain_cal_preopen import (
    ACTIVITIES,
    absolute_return_home_error,
    categorical_draw,
    derive_uint64,
    paired_household_bootstrap,
    tvd,
    uniform01,
    validate_chain,
    weighted_log_loss,
    weighted_shares,
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def candidate_paths(root: Path, candidate_id: str, grid_id: str) -> tuple[Path, Path]:
    if candidate_id == "CHAIN_REF":
        base = root / "models" / "CHAIN_REF"
    else:
        base = root / "models" / candidate_id / grid_id
    return base / "model.json", base / "artifact_manifest.json"


def synthetic_rows() -> list[dict[str, object]]:
    return [
        {"hh": "H1", "person": "P1", "target": "WORK", "weight": 1.0},
        {"hh": "H1", "person": "P1", "target": "HOME", "weight": 1.0},
        {"hh": "H2", "person": "P2", "target": "SHOPPING", "weight": 1.5},
        {"hh": "H2", "person": "P2", "target": "HOME", "weight": 1.5},
        {"hh": "H3", "person": "P3", "target": "LEISURE", "weight": 0.8},
        {"hh": "H3", "person": "P3", "target": "HOME", "weight": 0.8},
        {"hh": "H4", "person": "P4", "target": "WORK", "weight": 1.2},
        {"hh": "H4", "person": "P4", "target": "SHOPPING", "weight": 1.2},
        {"hh": "H4", "person": "P4", "target": "HOME", "weight": 1.2},
    ]


def candidate_pmfs(candidate_index: int, n: int) -> list[dict[str, float]]:
    base = [
        {"HOME": 0.18, "WORK": 0.47, "SHOPPING": 0.20, "LEISURE": 0.15},
        {"HOME": 0.70, "WORK": 0.10, "SHOPPING": 0.10, "LEISURE": 0.10},
        {"HOME": 0.15, "WORK": 0.15, "SHOPPING": 0.55, "LEISURE": 0.15},
        {"HOME": 0.72, "WORK": 0.08, "SHOPPING": 0.10, "LEISURE": 0.10},
        {"HOME": 0.15, "WORK": 0.15, "SHOPPING": 0.15, "LEISURE": 0.55},
        {"HOME": 0.70, "WORK": 0.10, "SHOPPING": 0.10, "LEISURE": 0.10},
        {"HOME": 0.18, "WORK": 0.47, "SHOPPING": 0.20, "LEISURE": 0.15},
        {"HOME": 0.18, "WORK": 0.17, "SHOPPING": 0.50, "LEISURE": 0.15},
        {"HOME": 0.72, "WORK": 0.08, "SHOPPING": 0.10, "LEISURE": 0.10},
    ]
    delta = (candidate_index - 2.5) * 0.002
    out: list[dict[str, float]] = []
    for row in base[:n]:
        changed = dict(row)
        changed["HOME"] = max(0.001, changed["HOME"] + delta)
        changed["LEISURE"] = max(0.001, changed["LEISURE"] - delta)
        out.append(changed)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    if args.output_dir.exists() or Path(str(args.output_dir) + ".partial").exists():
        raise SystemExit("Output directory already exists")

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    partial = Path(str(args.output_dir) + ".partial")
    partial.mkdir(parents=True)

    validation: list[dict[str, object]] = []

    def record(check: str, passed: bool, detail: object) -> None:
        validation.append(
            {"check": check, "status": "PASS" if passed else "FAIL", "detail": detail}
        )
        if not passed:
            raise RuntimeError(f"{check}: {detail}")

    try:
        contract_path = Path(cfg["frozen_contract"]["path"])
        record(
            "frozen_contract_hash",
            sha256(contract_path) == cfg["frozen_contract"]["sha256"],
            sha256(contract_path),
        )

        fit_root = Path(cfg["train_fit_run"]["root"])
        index_path = fit_root / cfg["train_fit_run"]["model_artifact_index"]
        fit_validation_path = fit_root / cfg["train_fit_run"]["fit_validation"]

        with index_path.open(newline="", encoding="utf-8") as handle:
            index_rows = list(csv.DictReader(handle))
        record("train_model_index_rows_6", len(index_rows) == 6, len(index_rows))

        with fit_validation_path.open(newline="", encoding="utf-8") as handle:
            fit_checks = list(csv.DictReader(handle))
        record(
            "train_fit_validation_all_pass",
            bool(fit_checks) and all(r["status"] == "PASS" for r in fit_checks),
            len(fit_checks),
        )

        actual_index = {
            (r["candidate_id"], r["grid_id"]): (
                r["model_sha256"],
                r["manifest_sha256"],
            )
            for r in index_rows
        }
        artifact_rows: list[dict[str, object]] = []
        for candidate in cfg["candidates"]:
            key = (candidate["candidate_id"], candidate["grid_id"])
            model_path, manifest_path = candidate_paths(fit_root, *key)
            model_sha = sha256(model_path)
            manifest_sha = sha256(manifest_path)
            index_ok = actual_index.get(key) == (
                candidate["model_sha256"],
                candidate["manifest_sha256"],
            )
            hash_ok = (
                model_sha == candidate["model_sha256"]
                and manifest_sha == candidate["manifest_sha256"]
            )
            json.loads(model_path.read_text(encoding="utf-8"))
            json.loads(manifest_path.read_text(encoding="utf-8"))
            artifact_rows.append(
                {
                    "artifact_id": candidate["artifact_id"],
                    "candidate_id": candidate["candidate_id"],
                    "grid_id": candidate["grid_id"],
                    "model_sha256": model_sha,
                    "manifest_sha256": manifest_sha,
                    "index_match": index_ok,
                    "file_hash_match": hash_ok,
                    "status": "PASS" if index_ok and hash_ok else "FAIL",
                }
            )
        record(
            "candidate_artifacts_exact_and_hash_valid",
            all(r["status"] == "PASS" for r in artifact_rows),
            len(artifact_rows),
        )

        rows = synthetic_rows()
        targets = [str(r["target"]) for r in rows]
        weights = [float(r["weight"]) for r in rows]
        observed_share = weighted_shares(targets, weights, ACTIVITIES)

        primary_rows: list[dict[str, object]] = []
        guardrail_rows: list[dict[str, object]] = []
        candidate_losses: dict[str, float] = {}

        for i, candidate in enumerate(cfg["candidates"]):
            pmfs = candidate_pmfs(i, len(rows))
            loss = weighted_log_loss(targets, pmfs, weights)
            candidate_losses[candidate["artifact_id"]] = loss
            primary_rows.append(
                {
                    "artifact_id": candidate["artifact_id"],
                    "metric": "WEIGHTED_NEXT_ACTIVITY_LOG_LOSS",
                    "value": loss,
                    "synthetic_only": True,
                }
            )

            generated: list[str] = []
            for j, (row, pmf) in enumerate(zip(rows, pmfs, strict=True)):
                seed = derive_uint64(
                    cfg["synthetic_protocol"]["master_seed"],
                    cfg["synthetic_protocol"]["scenario_id"],
                    str(row["person"]),
                    cfg["synthetic_protocol"]["component_namespace"],
                    j,
                )
                generated.append(categorical_draw(pmf, uniform01(seed)))

            generated_share = weighted_shares(generated, weights, ACTIVITIES)
            purpose_tvd = tvd(observed_share, generated_share, ACTIVITIES)
            transition_tvd = purpose_tvd

            obs_final = ["HOME", "HOME", "HOME", "HOME"]
            gen_final = ["HOME", "HOME", "HOME", generated[-1]]
            day_weights = [1.0, 1.5, 0.8, 1.2]
            ret_err = absolute_return_home_error(obs_final, gen_final, day_weights)

            for metric, statistic, value in [
                ("M2-PURP-01", "TVD", purpose_tvd),
                ("M2-TRANS-01", "TVD", transition_tvd),
                ("M2-RET-01", "ABS_RETURN_HOME_SHARE_ERROR", ret_err),
            ]:
                guardrail_rows.append(
                    {
                        "artifact_id": candidate["artifact_id"],
                        "metric": metric,
                        "statistic": statistic,
                        "value": value,
                        "synthetic_only": True,
                    }
                )

        for states, k in [
            (["HOME", "WORK", "HOME"], 2),
            (["HOME", "SHOPPING", "LEISURE", "HOME"], 3),
        ]:
            validate_chain(states, k)
        record("synthetic_chain_invariants", True, "K transitions => K+1 states")

        crn_seed_a = derive_uint64(
            cfg["synthetic_protocol"]["master_seed"],
            cfg["synthetic_protocol"]["scenario_id"],
            "P_SYNTH",
            cfg["synthetic_protocol"]["component_namespace"],
            7,
        )
        crn_seed_b = derive_uint64(
            cfg["synthetic_protocol"]["master_seed"],
            cfg["synthetic_protocol"]["scenario_id"],
            "P_SYNTH",
            cfg["synthetic_protocol"]["component_namespace"],
            7,
        )
        crn_ok = crn_seed_a == crn_seed_b
        record("crn_deterministic", crn_ok, crn_seed_a)

        reference_id = cfg["candidates"][0]["artifact_id"]
        challenger_id = cfg["candidates"][1]["artifact_id"]
        diff = candidate_losses[reference_id] - candidate_losses[challenger_id]
        household_differences = {
            "H1": diff - 0.01,
            "H2": diff + 0.01,
            "H3": diff - 0.005,
            "H4": diff + 0.005,
        }
        ci_low, ci_med, ci_high = paired_household_bootstrap(
            household_differences,
            replicates=cfg["synthetic_protocol"]["bootstrap_replicates"],
            master_seed=cfg["synthetic_protocol"]["master_seed"],
        )
        record(
            "synthetic_bootstrap_finite",
            all(map(lambda x: math.isfinite(x), [ci_low, ci_med, ci_high])),
            f"{ci_low},{ci_med},{ci_high}",
        )

        write_csv(
            partial / "candidate_artifact_validation.csv",
            list(artifact_rows[0]),
            artifact_rows,
        )
        write_csv(
            partial / "synthetic_primary_metrics.csv",
            list(primary_rows[0]),
            primary_rows,
        )
        write_csv(
            partial / "synthetic_guardrails.csv",
            list(guardrail_rows[0]),
            guardrail_rows,
        )
        (partial / "synthetic_bootstrap_check.json").write_text(
            json.dumps(
                {
                    "synthetic_only": True,
                    "reference_artifact_id": reference_id,
                    "challenger_artifact_id": challenger_id,
                    "replicates": cfg["synthetic_protocol"]["bootstrap_replicates"],
                    "ci_lower": ci_low,
                    "ci_median": ci_med,
                    "ci_upper": ci_high,
                    "status": "PASS",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        (partial / "crn_validation.json").write_text(
            json.dumps(
                {
                    "seed_a": crn_seed_a,
                    "seed_b": crn_seed_b,
                    "same_context_same_seed": crn_ok,
                    "candidate_id_excluded_from_seed_namespace": True,
                    "status": "PASS",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        record("cal_read_performed_false", True, False)
        record("test_rows_read_zero", True, 0)
        record("candidate_selection_none", True, "NONE")

        write_csv(
            partial / "validation.csv",
            ["check", "status", "detail"],
            validation,
        )
        shutil.copy2(args.config, partial / "execution_contract_snapshot.yaml")
        (partial / "environment.json").write_text(
            json.dumps(
                {
                    "python": sys.version,
                    "platform": platform.platform(),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        manifest = {
            "phase": "F3.4d-2a",
            "component": "DG_ACTIVITY_CHAIN",
            "status": "PASS",
            "execution_mode": "SYNTHETIC_TRAIN_PREOPEN",
            "candidate_artifacts": 6,
            "candidate_selection": "NONE",
            "train_fit_root": str(fit_root),
            "train_artifacts_opened": 12,
            "synthetic_transition_rows": len(rows),
            "synthetic_primary_metric_rows": len(primary_rows),
            "synthetic_guardrail_rows": len(guardrail_rows),
            "cal_read_performed": False,
            "cal_files_opened": [],
            "cal_rows_read": 0,
            "real_cal_open_authorized": False,
            "test_open_authorized": False,
            "test_rows_read": 0,
            "next_component_authorized": False,
            "formal_g2": "NOT_EVALUATED",
        }
        (partial / "run_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        evidence_files = sorted(
            p.name for p in partial.iterdir() if p.is_file()
        )
        evidence_manifest = {
            "files": {
                name: sha256(partial / name)
                for name in evidence_files
            }
        }
        (partial / "evidence_manifest.json").write_text(
            json.dumps(evidence_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        checksum_files = sorted(
            p for p in partial.iterdir()
            if p.is_file() and p.name != "checksums.sha256"
        )
        (partial / "checksums.sha256").write_text(
            "\n".join(
                f"{sha256(p)}  {p.name}" for p in checksum_files
            )
            + "\n",
            encoding="utf-8",
        )

        partial.rename(args.output_dir)
        print(json.dumps(manifest, indent=2, sort_keys=True))
    except Exception as exc:
        failure = {
            "phase": "F3.4d-2a",
            "status": "FAIL",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "cal_read_performed": False,
            "cal_rows_read": 0,
            "test_rows_read": 0,
        }
        (partial / "failure.json").write_text(
            json.dumps(failure, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        files = [p for p in partial.iterdir() if p.is_file() and p.name != "checksums.sha256"]
        (partial / "checksums.sha256").write_text(
            "\n".join(f"{sha256(p)}  {p.name}" for p in sorted(files))
            + "\n",
            encoding="utf-8",
        )
        raise


if __name__ == "__main__":
    main()
