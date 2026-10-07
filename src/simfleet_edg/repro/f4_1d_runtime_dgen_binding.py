from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any, cast

import pandas as pd
import yaml  # type: ignore[import-untyped]

from simfleet_edg.demand.m2_m3_adapter import adapt_joint_generated_frames
from simfleet_edg.demand.runtime_context import ScenarioDayContext, build_runtime_context
from simfleet_edg.demand.runtime_generator import ProductionDGenGenerator

EXPECTED_PARENT = "eebccc7a43eb7c1ef2661da3f357c0e5b01e72ef"
EXPECTED_PHASE = "F4.1d"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo_root, text=True).strip()


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected YAML mapping: {path}")
    return cast(dict[str, Any], payload)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_deterministic_csv_gz(frame: pd.DataFrame, path: Path) -> None:
    data = frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            stream.write(data)


def _read_population(path: Path) -> pd.DataFrame:
    upper = str(path).upper().replace("\\", "/")
    forbidden = ("CALIBRATION", "MID_TEST", "/TEST/", "1000A-1035")
    if any(token in upper for token in forbidden):
        raise RuntimeError(f"Forbidden CAL/TEST path in F4.1d: {path}")
    return pd.read_csv(path, low_memory=False)


def precheck(
    repo_root: Path,
    config_path: Path,
    population_run_dir: Path,
    *,
    post_push_git: bool,
    check_large_inputs: bool = True,
) -> dict[str, Any]:
    cfg = _load_yaml(config_path)
    checks: dict[str, bool] = {}
    checks["phase_exact"] = cfg.get("phase_id") == EXPECTED_PHASE
    checks["parent_contract_exact"] = cfg.get("required_parent_commit") == EXPECTED_PARENT

    if post_push_git:
        branch = _git(repo_root, "branch", "--show-current")
        head = _git(repo_root, "rev-parse", "HEAD")
        origin = _git(repo_root, "rev-parse", "origin/main")
        clean = _git(repo_root, "status", "--porcelain") == ""
        checks["branch_main"] = branch == "main"
        checks["head_pushed"] = head == origin and head != EXPECTED_PARENT
        checks["worktree_clean"] = clean

    population = cast(dict[str, Any], cfg["population"])
    paths = {
        "households": population_run_dir / str(population["households_filename"]),
        "persons": population_run_dir / str(population["persons_filename"]),
        "resources": population_run_dir / str(population["resources_filename"]),
    }
    if check_large_inputs:
        for name, path in paths.items():
            checks[f"{name}_exists"] = path.is_file()
            checks[f"{name}_sha256"] = (
                path.is_file() and sha256_file(path) == str(population[f"{name}_sha256"])
            )
        if all(path.is_file() for path in paths.values()):
            households = _read_population(paths["households"])
            persons = _read_population(paths["persons"])
            resources = _read_population(paths["resources"])
            checks["households_count"] = len(households) == int(population["households"])
            checks["persons_count"] = len(persons) == int(population["persons"])
            checks["resources_count"] = len(resources) == int(population["resources"])
    else:
        checks["large_inputs_deferred"] = True

    smoke = cast(dict[str, Any], cfg["smoke"])
    checks["smoke_population_512"] = int(smoke["population"]) == 512
    checks["smoke_scenario_exact"] = (
        str(smoke["scenario_id"]) == "F4_1D_BINDING_SMOKE_V1"
        and int(smoke["scenario_weekday"]) == 3
        and int(smoke["scenario_season"]) == 2
    )
    checks["downstream_forbidden"] = smoke.get("downstream_authorized") is False

    failed = sorted(name for name, passed in checks.items() if not passed)
    return {
        "phase": EXPECTED_PHASE,
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed": failed,
    }


def run_binding_smoke(
    repo_root: Path,
    config_path: Path,
    population_run_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    pre = precheck(
        repo_root,
        config_path,
        population_run_dir,
        post_push_git=True,
        check_large_inputs=True,
    )
    if pre["status"] != "PASS":
        raise RuntimeError(f"F4.1d precheck failed: {pre['failed']}")
    if output_dir.exists() or output_dir.with_name(output_dir.name + ".partial").exists():
        raise FileExistsError(f"Output path already exists: {output_dir}")

    cfg = _load_yaml(config_path)
    population = cast(dict[str, Any], cfg["population"])
    smoke = cast(dict[str, Any], cfg["smoke"])
    partial = output_dir.with_name(output_dir.name + ".partial")
    partial.mkdir(parents=True)

    households_path = population_run_dir / str(population["households_filename"])
    persons_path = population_run_dir / str(population["persons_filename"])
    resources_path = population_run_dir / str(population["resources_filename"])
    households = _read_population(households_path)
    persons = _read_population(persons_path)
    resources = _read_population(resources_path)

    scenario = ScenarioDayContext(
        scenario_id=str(smoke["scenario_id"]),
        scenario_weekday=int(smoke["scenario_weekday"]),
        scenario_season=int(smoke["scenario_season"]),
    )
    runtime = build_runtime_context(households, persons, resources, scenario)
    smoke_runtime = runtime.select_first_persons(int(smoke["population"]))

    generator = ProductionDGenGenerator(repo_root)
    generated = generator.generate(smoke_runtime)
    plans = adapt_joint_generated_frames(generated.day_rows, generated.trip_rows)

    expected_people = set(smoke_runtime.frame["source_person_id"].astype(str))
    plan_people = {plan.person_id for plan in plans}
    if plan_people != expected_people:
        raise RuntimeError("PersonDayPlan identities differ from accepted M1 smoke identities")
    if any(plan.household_id not in set(smoke_runtime.frame["source_household_id"].astype(str)) for plan in plans):
        raise RuntimeError("PersonDayPlan contains non-M1 household identity")

    outputs = cast(dict[str, Any], cfg["outputs"])
    _write_deterministic_csv_gz(
        smoke_runtime.frame,
        partial / str(outputs["runtime_context"]),
    )
    _write_deterministic_csv_gz(
        generated.day_rows,
        partial / str(outputs["day_rows"]),
    )
    _write_deterministic_csv_gz(
        generated.trip_rows,
        partial / str(outputs["trip_rows"]),
    )
    _write_json(partial / str(outputs["support_audit"]), generated.support_audit)
    pd.DataFrame(generated.artifact_validation).to_csv(
        partial / str(outputs["artifact_validation"]), index=False, lineterminator="\n"
    )
    adapter_check = {
        "status": "PASS",
        "plans": len(plans),
        "person_identity_exact": plan_people == expected_people,
        "household_identity_m1_only": True,
    }
    _write_json(partial / str(outputs["adapter_check"]), adapter_check)

    canonical_hashes = {
        name: sha256_file(partial / str(outputs[name]))
        for name in ("runtime_context", "day_rows", "trip_rows")
    }
    manifest = {
        "schema_version": "simfleet-edg-f4-1d-binding-run-v1",
        "phase": EXPECTED_PHASE,
        "status": "PASS",
        "git_commit": _git(repo_root, "rev-parse", "HEAD"),
        "origin_main": _git(repo_root, "rev-parse", "origin/main"),
        "scenario": {
            "scenario_id": scenario.scenario_id,
            "scenario_weekday": scenario.scenario_weekday,
            "scenario_season": scenario.scenario_season,
        },
        "master_seed": int(cfg["master_seed"]),
        "smoke_population": len(smoke_runtime.frame),
        "generated_day_rows": len(generated.day_rows),
        "generated_trip_rows": len(generated.trip_rows),
        "person_day_plans": len(plans),
        "canonical_output_sha256": canonical_hashes,
        "support_audit": generated.support_audit,
        "cal_read_count": 0,
        "mid_test_read_count": 0,
        "downstream_authorized": False,
        "full_100k_dgen_realization": False,
        "s_near_executed": False,
        "s_dist_executed": False,
        "s_attr_executed": False,
        "g3_opened": False,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "pid": os.getpid(),
        },
    }
    _write_json(partial / str(outputs["run_manifest"]), manifest)

    checksums = partial / "checksums.sha256"
    lines = []
    for path in sorted(partial.iterdir(), key=lambda item: item.name):
        if path.is_file() and path.name != checksums.name:
            lines.append(f"{sha256_file(path)}  {path.name}")
    checksums.write_text("\n".join(lines) + "\n", encoding="utf-8")
    partial.rename(output_dir)
    return manifest

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--population-run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--precheck-only", action="store_true")
    parser.add_argument("--post-push-git", action="store_true")
    parser.add_argument("--skip-large-inputs", action="store_true")
    args = parser.parse_args()

    repo_root = args.repo_root.expanduser().resolve()
    config_path = args.config.expanduser().resolve()
    population_run_dir = args.population_run_dir.expanduser().resolve()
    if args.precheck_only:
        result = precheck(
            repo_root,
            config_path,
            population_run_dir,
            post_push_git=args.post_push_git,
            check_large_inputs=not args.skip_large_inputs,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1

    if args.output_dir is None:
        parser.error("--output-dir is required unless --precheck-only is used")
    result = run_binding_smoke(repo_root, config_path, population_run_dir, args.output_dir.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
