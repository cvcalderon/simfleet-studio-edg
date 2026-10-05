"""Commit-bound controlled CAL runner for F1-P_CONSTR-CAL-01.

The tracked protocol authorization permits building this runner. Actual CAL payload
parsing requires a separate positive execution authorization outside the repository,
bound to the exact synchronized runner commit.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import platform
import subprocess
import sys
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from simfleet_edg.common.population_materializer import (
    _recode_license,
    _stock_quantity,
    age_infr_class,
    load_activity_recoding,
)
from simfleet_edg.common.population_split import normalize_source_id, parse_float, parse_int
from simfleet_edg.population.calibration_evaluation import (
    FamilyResult,
    bike_ebike_family_error,
    bootstrap_materiality_threshold,
    conditional_tvd_family,
    select_constrained_variant,
    select_final_candidate,
    stock_category,
)

PROTOCOL_AUTH_COMMIT = "2313ef1689037bcb45812e896324585d8988b4bf"
PHASE_ID = "F1-P_CONSTR-CAL-01"
VARIANTS = (
    "P_TRS_V1_FINAL",
    "P_CONSTR_RMIN_V2_HD_U",
    "P_CONSTR_RMIN_V2_HD_W",
)
PRIMARY_FAMILIES = (
    "ACTIVITY_BY_AGE",
    "LICENSE_BY_AGE_SEX",
    "HH_CAR_STOCK_BY_SIZE",
    "HH_BIKE_EBIKE_STOCK_BY_SIZE",
)


class AuthorizationError(RuntimeError):
    """Raised before CAL payload parsing or staging creation is allowed."""


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo_root, text=True).strip()


def repository_state(repo_root: Path) -> dict[str, str]:
    return {
        "branch": _git(repo_root, "branch", "--show-current"),
        "head": _git(repo_root, "rev-parse", "HEAD"),
        "origin_main": _git(repo_root, "rev-parse", "origin/main"),
        "porcelain": _git(repo_root, "status", "--porcelain"),
    }


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _outside_repo(path: Path, repo_root: Path) -> bool:
    try:
        path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return True
    return False


def validate_execution_authorization(
    authorization_path: Path,
    repo_root: Path,
    *,
    impl03_expected_sha256: str,
) -> dict[str, Any]:
    """Fail closed before CAL payload parsing or output staging creation."""
    if not authorization_path.is_file():
        raise AuthorizationError("Execution authorization file missing")
    if not _outside_repo(authorization_path, repo_root):
        raise AuthorizationError("Positive execution authorization must be outside repository")

    payload = json.loads(authorization_path.read_text(encoding="utf-8"))
    state = repository_state(repo_root)
    checks = {
        "schema": payload.get("schema_version")
        == "simfleet-edg-f1-pconstr-cal01-execution-authorization-v1",
        "phase": payload.get("phase_id") == PHASE_ID,
        "authorized": payload.get("authorized") is True,
        "status": payload.get("authorization_status") == "AUTHORIZED_A1",
        "protocol_commit": payload.get("protocol_authorization_commit")
        == PROTOCOL_AUTH_COMMIT,
        "branch_main": state["branch"] == "main",
        "head_origin_equal": state["head"] == state["origin_main"],
        "worktree_clean": state["porcelain"] == "",
        "runner_commit_exact": payload.get("authorized_runner_commit") == state["head"],
        "cal_only": payload.get("allowed_partition") == "CALIBRATION_ONLY",
        "cal_open": payload.get("cal_open_authorized") is True,
        "impl03_exact": payload.get("impl03_runbundle_sha256")
        == impl03_expected_sha256,
        "selection_none": payload.get("candidate_selection_at_entry") == "NONE",
        "thresholds_unfrozen": payload.get("g1_thresholds_before_run") == "NOT_FROZEN",
        "test_closed": payload.get("mid_test_open_authorized") is False,
        "holdout_closed": payload.get("holdout_1000A_1035_open_authorized") is False,
        "plr_closed": payload.get("plr_allocation_authorized") is False,
        "f3_closed": payload.get("f3_modification_authorized") is False,
    }
    failed = [name for name, passed in checks.items() if not bool(passed)]
    if failed:
        raise AuthorizationError(f"Execution authorization rejected: {failed}")
    return {**payload, "repository_head": state["head"], "checks": checks}


def _route_id_from_raw_line(line: str, index: int) -> str:
    parts = line.split(",", index + 1)
    if len(parts) <= index:
        return ""
    return normalize_source_id(parts[index].strip().strip('"'))


def selective_csv_rows(
    path: Path,
    *,
    allowed_household_ids: set[str],
    household_id_index: int,
    required_columns: Iterable[str],
) -> pd.DataFrame:
    """Parse full payload only for authorized household IDs.

    Non-authorized lines are traversed solely to inspect the routing H_ID token; their
    remaining payload fields are not CSV-parsed or materialized.
    """
    required = list(required_columns)
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        header_line = handle.readline()
        header = next(csv.reader([header_line]))
        missing = set(required).difference(header)
        if missing:
            raise ValueError(f"{path.name} missing required columns: {sorted(missing)}")
        if header[household_id_index] != "H_ID":
            raise ValueError(f"Unexpected H_ID routing column position in {path.name}")
        index = {name: header.index(name) for name in required}
        for raw_line in handle:
            household_id = _route_id_from_raw_line(raw_line, household_id_index)
            if household_id not in allowed_household_ids:
                continue
            values = next(csv.reader([raw_line]))
            rows.append({name: values[pos] for name, pos in index.items()})
    return pd.DataFrame(rows, columns=required)


def _cal_household_ids(split_path: Path) -> tuple[pd.DataFrame, set[str]]:
    split = pd.read_csv(split_path)
    required = {
        "source_household_id",
        "split",
        "is_private_household",
        "joint_rmin_donor_eligible",
        "class",
    }
    missing = required.difference(split.columns)
    if missing:
        raise ValueError(f"SplitManifest missing columns: {sorted(missing)}")
    cal = split[split["split"].eq("CALIBRATION")].copy()
    cal["source_household_id"] = cal["source_household_id"].map(normalize_source_id)
    private = cal[cal["is_private_household"].astype(bool)].copy()
    return cal, set(private["source_household_id"].astype(str))


def _build_cal_reference(
    households_path: Path,
    persons_path: Path,
    split_path: Path,
    activity_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    split_cal, private_ids = _cal_household_ids(split_path)
    hh_cols = (
        "H_ID", "H_GEW", "H_ART", "H_GR", "H_ANZAUTO", "H_ANZRAD", "H_ANZPED", "BLAND"
    )
    person_cols = (
        "HP_ID", "H_ID", "P_GEW", "HP_SEX", "HP_ALTER", "HP_TAET", "P_FS_PKW", "BLAND"
    )
    households = selective_csv_rows(
        households_path,
        allowed_household_ids=private_ids,
        household_id_index=0,
        required_columns=hh_cols,
    )
    persons = selective_csv_rows(
        persons_path,
        allowed_household_ids=private_ids,
        household_id_index=1,
        required_columns=person_cols,
    )
    if len(households) != len(private_ids):
        raise ValueError(f"Private CAL household materialization mismatch: {len(households)} != {len(private_ids)}")

    activity_map = load_activity_recoding(activity_path)
    hh_rows: list[dict[str, Any]] = []
    for raw in households.to_dict("records"):
        if parse_int(raw["BLAND"]) != 11 or parse_int(raw["H_ART"]) not in {1, 2}:
            raise ValueError("Non-private/non-Berlin household reached CAL reference")
        hid = normalize_source_id(raw["H_ID"])
        size = parse_int(raw["H_GR"])
        row: dict[str, Any] = {
            "source_household_id": hid,
            "H_GEW": parse_float(raw["H_GEW"]),
            "household_size_class": "6_PLUS" if size == 6 else str(size),
        }
        for source, out, cap in (
            ("H_ANZAUTO", "car", 3),
            ("H_ANZRAD", "bike", 10),
            ("H_ANZPED", "ebike", 10),
        ):
            quantity, _, observation = _stock_quantity(raw[source], cap)
            row[f"{out}_observation_status"] = observation
            row[f"{out}_stock_category"] = (
                stock_category(quantity, cap=cap) if quantity is not None else "UNKNOWN"
            )
        hh_rows.append(row)

    person_rows: list[dict[str, Any]] = []
    for raw in persons.to_dict("records"):
        if parse_int(raw["BLAND"]) != 11:
            continue
        sex_code = parse_int(raw["HP_SEX"])
        age = parse_int(raw["HP_ALTER"])
        if sex_code not in {1, 2} or not 0 <= age <= 85:
            continue
        activity_code = parse_int(raw["HP_TAET"])
        if activity_code not in activity_map:
            raise ValueError(f"Activity code absent from frozen recoding: {activity_code}")
        activity = activity_map[activity_code][0]
        license_value, license_observation = _recode_license(raw["P_FS_PKW"])
        person_rows.append(
            {
                "source_household_id": normalize_source_id(raw["H_ID"]),
                "source_person_id": normalize_source_id(raw["HP_ID"]),
                "P_GEW": parse_float(raw["P_GEW"]),
                "age_infr_class": age_infr_class(age),
                "sex": {1: "MALE", 2: "FEMALE"}[sex_code],
                "primary_activity_status": activity,
                "activity_observation_status": (
                    "MISSING_RESPONSE" if activity_code == 99 else "OBSERVED"
                ),
                "car_driver_license": license_value,
                "license_observation_status": license_observation,
            }
        )

    hh_ref = pd.DataFrame(hh_rows)
    person_ref = pd.DataFrame(person_rows)
    if set(person_ref["source_household_id"]).difference(private_ids):
        raise AssertionError("Non-CAL person materialized")
    access = {
        "split_cal_households_all": int(len(split_cal)),
        "split_cal_households_strict": int(split_cal["joint_rmin_donor_eligible"].astype(bool).sum()),
        "private_cal_households_materialized": int(len(hh_ref)),
        "private_cal_person_rows_materialized": int(len(person_ref)),
        "private_cal_household_ids_sha256": sha256_bytes("\n".join(sorted(private_ids, key=int)).encode()),
        "household_reference_sha256": sha256_bytes(hh_ref.sort_values("source_household_id", key=lambda s: s.astype(int)).to_csv(index=False, lineterminator="\n").encode()),
        "person_reference_sha256": sha256_bytes(person_ref.sort_values("source_person_id", key=lambda s: s.astype(int)).to_csv(index=False, lineterminator="\n").encode()),
        "test_rows_materialized": 0,
        "holdout_1000A_1035_read": False,
        "non_cal_payload_policy": "ROUTING_IDENTIFIER_ONLY_NONCAL_PAYLOAD_NOT_PARSED_OR_MATERIALIZED",
    }
    return hh_ref, person_ref, access


def _zip_member_name(run_id: str, variant: str, kind: str) -> str:
    return f"{run_id}/S_{variant}_{kind}.csv"


def _load_candidates(
    impl03_zip: Path,
    cfg: dict[str, Any],
) -> tuple[dict[str, dict[str, pd.DataFrame]], list[dict[str, Any]], dict[str, Any]]:
    expected_zip = cfg["candidate_runbundle"]["sha256"]
    actual_zip = sha256_file(impl03_zip)
    if actual_zip != expected_zip:
        raise ValueError("IMPL-03 RunBundle SHA256 mismatch")
    run_id = cfg["candidate_runbundle"]["run_id"]
    out: dict[str, dict[str, pd.DataFrame]] = {}
    validations: list[dict[str, Any]] = []
    with zipfile.ZipFile(impl03_zip) as archive:
        manifest = json.loads(archive.read(f"{run_id}/manifest.json"))
        if manifest.get("status") != "PASS" or manifest.get("candidate_selection") != "DEFERRED_TO_CAL":
            raise ValueError("Unexpected IMPL-03 manifest state")
        for variant in VARIANTS:
            out[variant] = {}
            for kind in ("households", "persons", "resources"):
                spec = cfg["candidate_runbundle"]["variants"][variant][kind]
                name = _zip_member_name(run_id, variant, kind)
                data = archive.read(name)
                actual_sha = sha256_bytes(data)
                if actual_sha != spec["sha256"]:
                    raise ValueError(f"Candidate inner SHA mismatch: {variant}/{kind}")
                frame = pd.read_csv(io.BytesIO(data))
                if len(frame) != int(spec["rows"]):
                    raise ValueError(f"Candidate row mismatch: {variant}/{kind}")
                out[variant][kind] = frame
                validations.append({
                    "input_id": f"{variant}/{kind}",
                    "expected_rows": int(spec["rows"]),
                    "actual_rows": int(len(frame)),
                    "expected_sha256": str(spec["sha256"]),
                    "actual_sha256": actual_sha,
                    "status": "PASS",
                })
    return out, validations, manifest


def _synthetic_household_stock(
    households: pd.DataFrame,
    resources: pd.DataFrame,
    resource_type: str,
    cap: int,
) -> pd.DataFrame:
    sizes = households[["household_id", "materialized_member_count"]].copy()
    sizes["household_size_class"] = sizes["materialized_member_count"].astype(int).map(
        lambda value: "6_PLUS" if value >= 6 else str(value)
    )
    frame = resources[
        resources["scope"].eq("HOUSEHOLD")
        & resources["resource_type"].eq(resource_type)
        & resources["observation_status"].eq("OBSERVED")
    ][["household_id", "quantity"]].copy()
    frame = frame.merge(sizes[["household_id", "household_size_class"]], on="household_id", how="left", validate="one_to_one")
    if frame["household_size_class"].isna().any():
        raise ValueError(f"Synthetic {resource_type} household-size join failed")
    frame["stock_category"] = frame["quantity"].map(lambda value: stock_category(value, cap=cap))
    frame["unit_weight"] = 1.0
    return frame


def _reference_stock(hh_ref: pd.DataFrame, prefix: str) -> pd.DataFrame:
    return hh_ref[hh_ref[f"{prefix}_observation_status"].eq("OBSERVED")][
        ["source_household_id", "H_GEW", "household_size_class", f"{prefix}_stock_category"]
    ].rename(columns={f"{prefix}_stock_category": "stock_category"})


def _evaluate_variant(
    hh_ref: pd.DataFrame,
    person_ref: pd.DataFrame,
    candidate: dict[str, pd.DataFrame],
    activity_categories: list[str],
) -> tuple[dict[str, FamilyResult], dict[str, FamilyResult]]:
    persons = candidate["persons"].copy()
    persons["unit_weight"] = 1.0
    activity_ref = person_ref[person_ref["activity_observation_status"].eq("OBSERVED")]
    activity_syn = persons[persons["activity_observation_status"].eq("OBSERVED")]
    activity = conditional_tvd_family(
        activity_ref,
        activity_syn,
        family_id="ACTIVITY_BY_AGE",
        condition_cols=["age_infr_class"],
        outcome_col="primary_activity_status",
        reference_weight_col="P_GEW",
        synthetic_weight_col="unit_weight",
        categories=activity_categories,
    )
    license_ref = person_ref[person_ref["license_observation_status"].eq("OBSERVED")]
    license_syn = persons[persons["license_observation_status"].eq("OBSERVED")]
    license_result = conditional_tvd_family(
        license_ref,
        license_syn,
        family_id="LICENSE_BY_AGE_SEX",
        condition_cols=["age_infr_class", "sex"],
        outcome_col="car_driver_license",
        reference_weight_col="P_GEW",
        synthetic_weight_col="unit_weight",
        categories=["YES", "NO"],
    )
    car_ref = _reference_stock(hh_ref, "car")
    car_syn = _synthetic_household_stock(candidate["households"], candidate["resources"], "CAR", 3)
    car = conditional_tvd_family(
        car_ref,
        car_syn,
        family_id="HH_CAR_STOCK_BY_SIZE",
        condition_cols=["household_size_class"],
        outcome_col="stock_category",
        reference_weight_col="H_GEW",
        synthetic_weight_col="unit_weight",
        categories=["ZERO", "ONE", "TWO", "THREE_PLUS"],
    )
    bike_ref = _reference_stock(hh_ref, "bike")
    ebike_ref = _reference_stock(hh_ref, "ebike")
    bike_syn = _synthetic_household_stock(candidate["households"], candidate["resources"], "BIKE", 10)
    ebike_syn = _synthetic_household_stock(candidate["households"], candidate["resources"], "EBIKE", 10)
    stock_categories = ["ZERO", "ONE", "TWO_TO_NINE", "TEN_PLUS"]
    bike = conditional_tvd_family(
        bike_ref,
        bike_syn,
        family_id="HH_BIKE_STOCK_BY_SIZE",
        condition_cols=["household_size_class"],
        outcome_col="stock_category",
        reference_weight_col="H_GEW",
        synthetic_weight_col="unit_weight",
        categories=stock_categories,
    )
    ebike = conditional_tvd_family(
        ebike_ref,
        ebike_syn,
        family_id="HH_EBIKE_STOCK_BY_SIZE",
        condition_cols=["household_size_class"],
        outcome_col="stock_category",
        reference_weight_col="H_GEW",
        synthetic_weight_col="unit_weight",
        categories=stock_categories,
    )
    bike_family = bike_ebike_family_error(bike, ebike)
    primary = {
        activity.family_id: activity,
        license_result.family_id: license_result,
        car.family_id: car,
        bike_family.family_id: bike_family,
    }
    return primary, {bike.family_id: bike, ebike.family_id: ebike}


def _expand_by_households(frame: pd.DataFrame, sampled_ids: list[str]) -> pd.DataFrame:
    groups = {str(key): group for key, group in frame.groupby("source_household_id", sort=False)}
    pieces = [groups[hid].copy() for hid in sampled_ids if hid in groups]
    if not pieces:
        return frame.iloc[0:0].copy()
    return pd.concat(pieces, ignore_index=True)


def _thresholds(
    hh_ref: pd.DataFrame,
    person_ref: pd.DataFrame,
    ptrs: dict[str, pd.DataFrame],
    activity_categories: list[str],
    baseline: dict[str, FamilyResult],
) -> dict[str, float]:
    household_ids = hh_ref["source_household_id"].astype(str).tolist()
    thresholds: dict[str, float] = {}
    for family_id in PRIMARY_FAMILIES:
        def error_fn(sampled: list[str], family_id: str = family_id) -> float:
            hh_boot = _expand_by_households(hh_ref, sampled)
            p_boot = _expand_by_households(person_ref, sampled)
            primary, _ = _evaluate_variant(hh_boot, p_boot, ptrs, activity_categories)
            return float(primary[family_id].error)
        thresholds[family_id] = bootstrap_materiality_threshold(
            household_ids,
            error_fn,
            family_id=family_id,
            baseline_error=float(baseline[family_id].error),
        )
    return thresholds


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_checksums(out: Path) -> None:
    target = out / "checksums.sha256"
    lines = [
        f"{sha256_file(path)}  {path.name}"
        for path in sorted(out.iterdir())
        if path.is_file() and path.name != target.name
    ]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_controlled_cal(
    repo_root: Path,
    config_path: Path,
    authorization_path: Path,
    impl03_runbundle_zip: Path,
    output_dir: Path,
) -> Path:
    repo_root = repo_root.resolve()
    config_path = config_path.resolve()
    authorization_path = authorization_path.resolve()
    output_dir = output_dir.resolve()
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    # CRITICAL ORDER: positive commit-bound execution authorization before CAL I/O/staging.
    auth = validate_execution_authorization(
        authorization_path,
        repo_root,
        impl03_expected_sha256=str(cfg["candidate_runbundle"]["sha256"]),
    )
    if not _outside_repo(output_dir, repo_root):
        raise AuthorizationError("RunBundle output must be outside repository")
    partial = Path(f"{output_dir}.partial")
    if output_dir.exists() or partial.exists():
        raise FileExistsError("Output or .partial staging already exists")

    # Frozen non-CAL assets may be validated after authorization and before CAL parsing.
    split_path = repo_root / cfg["sources"]["split_manifest"]["path"]
    activity_path = repo_root / cfg["sources"]["activity_recoding"]["path"]
    if sha256_file(split_path) != cfg["sources"]["split_manifest"]["sha256"]:
        raise ValueError("SplitManifest SHA mismatch")
    if sha256_file(activity_path) != cfg["sources"]["activity_recoding"]["sha256"]:
        raise ValueError("Activity recoding SHA mismatch")
    households_path = repo_root / cfg["sources"]["mid_households"]["path"]
    persons_path = repo_root / cfg["sources"]["mid_persons"]["path"]
    for key, path in (("mid_households", households_path), ("mid_persons", persons_path)):
        expected_size = int(cfg["sources"][key]["expected_file_size_bytes"])
        if not path.is_file() or path.stat().st_size != expected_size:
            raise ValueError(f"{key} path/size mismatch")

    candidate_data, candidate_validations, impl03_manifest = _load_candidates(
        impl03_runbundle_zip.resolve(), cfg
    )

    partial.mkdir(parents=True, exist_ok=False)
    try:
        hh_ref, person_ref, access = _build_cal_reference(
            households_path, persons_path, split_path, activity_path
        )
        if access["split_cal_households_all"] != int(cfg["cal_reference"]["expected_split_households_all"]):
            raise ValueError("Unexpected CAL household split count")
        if access["split_cal_households_strict"] != int(cfg["cal_reference"]["expected_strict_households"]):
            raise ValueError("Unexpected strict CAL household count")
        if access["private_cal_households_materialized"] != int(cfg["cal_reference"]["expected_private_households"]):
            raise ValueError("Unexpected private CAL household count")

        activity_map = load_activity_recoding(activity_path)
        activity_categories = sorted({value[0] for value in activity_map.values()})
        primary_by_variant: dict[str, dict[str, FamilyResult]] = {}
        sub_by_variant: dict[str, dict[str, FamilyResult]] = {}
        metric_rows: list[dict[str, Any]] = []
        submetric_rows: list[dict[str, Any]] = []
        for variant in VARIANTS:
            primary, sub = _evaluate_variant(hh_ref, person_ref, candidate_data[variant], activity_categories)
            primary_by_variant[variant] = primary
            sub_by_variant[variant] = sub
            for family_id, result in primary.items():
                metric_rows.append({
                    "variant_id": variant,
                    "family_id": family_id,
                    "error": result.error,
                    "decision_cells": result.decision_cells,
                    "low_n_cells": result.low_n_cells,
                })
            for family_id, result in sub.items():
                submetric_rows.append({
                    "variant_id": variant,
                    "submetric_id": family_id,
                    "error": result.error,
                    "decision_cells": result.decision_cells,
                    "low_n_cells": result.low_n_cells,
                })

        baseline = primary_by_variant["P_TRS_V1_FINAL"]
        thresholds = _thresholds(
            hh_ref, person_ref, candidate_data["P_TRS_V1_FINAL"], activity_categories, baseline
        )
        threshold_rows = [
            {
                "family_id": family,
                "baseline_error": baseline[family].error,
                "tau_proposed": thresholds[family],
                "bootstrap_replicates": 1000,
                "quantile": 0.95,
                "quantile_method": "higher",
                "role": "PROPOSED_AWAITING_MAIN_FREEZE",
            }
            for family in PRIMARY_FAMILIES
        ]
        errors_u = {k: v.error for k, v in primary_by_variant["P_CONSTR_RMIN_V2_HD_U"].items()}
        errors_w = {k: v.error for k, v in primary_by_variant["P_CONSTR_RMIN_V2_HD_W"].items()}
        constrained = select_constrained_variant(errors_u, errors_w, thresholds)
        constrained_errors = {k: v.error for k, v in primary_by_variant[constrained].items()}
        ptrs_errors = {k: v.error for k, v in baseline.items()}
        fit = cfg["candidate_runbundle"]["variants"]
        selected = select_final_candidate(
            constrained,
            constrained_errors,
            ptrs_errors,
            thresholds,
            constrained_fit_l1=int(fit[constrained]["fit_l1"]),
            constrained_fit_max_abs=int(fit[constrained]["fit_max_abs"]),
            ptrs_fit_l1=int(fit["P_TRS_V1_FINAL"]["fit_l1"]),
            ptrs_fit_max_abs=int(fit["P_TRS_V1_FINAL"]["fit_max_abs"]),
            engineering_gate_pass=True,
        )
        selection = {
            "stage_1_constrained_proposal": constrained,
            "stage_2_final_candidate_proposal": selected,
            "selection_role": "PROPOSED_BY_FROZEN_CAL_RULES_AWAITING_MAIN_FREEZE",
            "g1_thresholds_role": "PROPOSED_AWAITING_MAIN_FREEZE",
            "holdout_1000A_1035_authorized": False,
            "mid_test_authorized": False,
        }

        pd.DataFrame(candidate_validations).to_csv(partial / "input_validation.csv", index=False)
        pd.DataFrame(metric_rows).to_csv(partial / "family_metrics.csv", index=False)
        pd.DataFrame(submetric_rows).to_csv(partial / "family_submetrics.csv", index=False)
        pd.DataFrame(threshold_rows).to_csv(partial / "thresholds_proposed.csv", index=False)
        _write_json(partial / "selection_proposal.json", selection)
        _write_json(partial / "authorization_snapshot.json", auth)
        (partial / "config_snapshot.yaml").write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")
        _write_json(partial / "cal_access_manifest.json", access)
        validation_rows = [
            {"check": "execution_authorization", "status": "PASS", "detail": auth["repository_head"]},
            {"check": "split_manifest_hash", "status": "PASS", "detail": cfg["sources"]["split_manifest"]["sha256"]},
            {"check": "impl03_runbundle_hash", "status": "PASS", "detail": cfg["candidate_runbundle"]["sha256"]},
            {"check": "test_rows_materialized_zero", "status": "PASS", "detail": "0"},
            {"check": "holdout_1000A_1035_unread", "status": "PASS", "detail": "true"},
            {"check": "candidate_selection_only_proposed", "status": "PASS", "detail": selected},
            {"check": "thresholds_only_proposed", "status": "PASS", "detail": "4"},
        ]
        pd.DataFrame(validation_rows).to_csv(partial / "validation.csv", index=False)
        pd.DataFrame(columns=["severity", "code", "detail"]).to_csv(partial / "issues.csv", index=False)
        _write_json(partial / "environment.json", {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
        })
        _write_json(partial / "run_manifest.json", {
            "schema_version": "simfleet-edg-f1-pconstr-cal01-runbundle-v1",
            "phase_id": PHASE_ID,
            "status": "PASS",
            "git_commit": auth["repository_head"],
            "protocol_authorization_commit": PROTOCOL_AUTH_COMMIT,
            "impl03_runbundle_sha256": cfg["candidate_runbundle"]["sha256"],
            "impl03_status": impl03_manifest.get("status"),
            "calibration_private_households_materialized": access["private_cal_households_materialized"],
            "calibration_person_rows_materialized": access["private_cal_person_rows_materialized"],
            "test_rows_materialized": 0,
            "candidate_selection_at_entry": "NONE",
            "candidate_proposal": selected,
            "g1_thresholds_v1": "NOT_FROZEN_PROPOSAL_ONLY",
            "holdout_1000A_1035_read": False,
            "spatial_plr_allocation": False,
            "f3_modified": False,
        })
        _write_checksums(partial)
        partial.rename(output_dir)
    except Exception:
        # Preserve authorized partial evidence if staging was created.
        raise
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--authorization-json", required=True, type=Path)
    parser.add_argument("--impl03-runbundle", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    out = run_controlled_cal(
        args.repo_root,
        args.config,
        args.authorization_json,
        args.impl03_runbundle,
        args.output_dir,
    )
    print(json.dumps({"status": "PASS", "output": str(out)}, indent=2))


if __name__ == "__main__":
    main()
