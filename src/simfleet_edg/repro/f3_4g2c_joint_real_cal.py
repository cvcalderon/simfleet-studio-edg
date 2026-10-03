from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from simfleet_edg.evaluation.activity_chain_cal_real import (
    _load_purpose_artifact,
    _record_by_id,
    _run_generated_guardrails,
)
from simfleet_edg.evaluation.cal_joint_gate import JointGateInput, joint_cal_gate
from simfleet_edg.evaluation.cal_metrics import (
    total_variation_distance,
    wasserstein_1d,
    weighted_distribution,
    weighted_mean,
    weighted_quantile,
)
from simfleet_edg.evaluation.time_schedule_cal_real import (
    _merge_time_context,
    _validate_source_temporal_rows,
)
from simfleet_edg.repro.f3_4g2a_joint_synthetic import generate_pipeline, load_pipeline
from simfleet_edg.repro.f3_4g2b_joint_real_cal_auth import (
    load_joint_real_cal_authorization,
)

REPO_ROOT = Path.cwd()
JOINT_REGISTRY = REPO_ROOT / "configs/f3/f3_4g1_joint_pipeline_registry_v1.json"
METRIC_MATRIX = REPO_ROOT / "docs/F3_4G1_JOINT_METRIC_MATRIX_v1.csv"
PRIMARY_WITNESS = REPO_ROOT / "docs/F3_4G1_PRIMARY_EVIDENCE_WITNESS_v1.csv"
REPLICATES = 32
COND_DIMS = (
    "age_infr_class",
    "sex",
    "primary_activity_status",
    "household_size_class",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_checksums(output: Path) -> None:
    target = output / "checksums.sha256"
    rows = [
        f"{sha256_file(path)}  {path.name}"
        for path in sorted(output.iterdir())
        if path.is_file() and path.name != target.name
    ]
    target.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _validate_input(path: Path, expected_sha: str, expected_rows: int) -> pd.DataFrame:
    actual_sha = sha256_file(path)
    if actual_sha != expected_sha:
        raise ValueError(f"CAL SHA mismatch: {path.name}")
    frame = pd.read_csv(path)
    if len(frame) != expected_rows:
        raise ValueError(
            f"CAL row mismatch for {path.name}: {len(frame)} != {expected_rows}"
        )
    return frame


def load_joint_cal_inputs(
    repo_root: Path,
    cfg: dict[str, Any],
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, dict[str, Any]]:
    root = repo_root / cfg["cal_input"]["root"]
    frames: dict[str, pd.DataFrame] = {}
    validation_rows: list[dict[str, Any]] = []
    opened: list[str] = []
    row_map: dict[str, int] = {}

    keys = (
        "person_day_context",
        "participation",
        "trip_count",
        "chain_days",
        "chain_transitions",
        "time_trips",
        "distance_raw",
        "distance_expanded_sensitivity",
    )
    for key in keys:
        spec = cfg["cal_input"][key]
        path = root / str(spec["filename"])
        frame = _validate_input(
            path,
            str(spec["sha256"]),
            int(spec["expected_rows"]),
        )
        frames[key] = frame
        opened.append(str(path.relative_to(repo_root)))
        row_map[path.name] = len(frame)
        validation_rows.append(
            {
                "input_id": key,
                "filename": path.name,
                "expected_rows": int(spec["expected_rows"]),
                "actual_rows": len(frame),
                "expected_sha256": str(spec["sha256"]),
                "actual_sha256": sha256_file(path),
                "status": "PASS",
            }
        )

    total = sum(row_map.values())
    if total != int(cfg["cal_input"]["expected_total_physical_rows"]):
        raise ValueError("Unexpected Joint CAL physical row total")

    context = frames["person_day_context"]
    if context["row_id"].duplicated().any():
        raise ValueError("person_day_context.row_id must be unique")

    access = {
        "cal_partition": "OPENED_AUTHORIZED_F3_4G2C_A1",
        "cal_files_opened": opened,
        "cal_file_rows": row_map,
        "cal_rows_read_total_physical": total,
        "test_partition": "SEALED",
        "test_files_opened": [],
        "test_rows_read": 0,
    }
    return frames, pd.DataFrame(validation_rows), access


def _merge_target_context(
    target: pd.DataFrame,
    context: pd.DataFrame,
    *,
    target_name: str,
    validate: str,
) -> pd.DataFrame:
    merged = target.merge(
        context,
        left_on="context_row_id",
        right_on="row_id",
        how="left",
        validate=validate,
        suffixes=("_target", "_context"),
    )
    if len(merged) != len(target) or merged["row_id"].isna().any():
        raise ValueError(f"{target_name}/context CAL join failed")
    for field in ("source_household_id", "source_person_id"):
        left = merged[f"{field}_target"].astype(str)
        right = merged[f"{field}_context"].astype(str)
        if not left.equals(right):
            raise ValueError(f"{field} mismatch in {target_name}/context")
    return merged


def _day_matrix(
    generated_days: pd.DataFrame,
    pipeline: str,
    context_ids: list[str],
    value_column: str,
) -> np.ndarray:
    frame = generated_days.loc[generated_days["pipeline"].eq(pipeline)].copy()
    frame["row_id"] = frame["row_id"].astype(str)
    lookup = {
        (int(row["replicate_index"]), str(row["row_id"])): row[value_column]
        for _, row in frame.iterrows()
    }
    out = np.empty((REPLICATES, len(context_ids)), dtype=float)
    for replicate in range(REPLICATES):
        for index, context_id in enumerate(context_ids):
            key = (replicate, context_id)
            if key not in lookup:
                raise ValueError(f"Missing generated day result for {key}")
            out[replicate, index] = float(lookup[key])
    return out


def _weighted_share(values: np.ndarray, weights: np.ndarray) -> float:
    return float(np.average(values.astype(float), weights=weights))


def participation_metrics(
    participation: pd.DataFrame,
    context: pd.DataFrame,
    generated_days: pd.DataFrame,
    pipeline: str,
) -> dict[str, float]:
    merged = _merge_target_context(
        participation,
        context,
        target_name="participation",
        validate="one_to_one",
    )
    if len(merged) != 460:
        raise ValueError("Unexpected Joint Participation evaluation rows")

    observed = merged["target_trip_day"].astype(int).to_numpy()
    weights = merged["fit_weight_P_GEW_target"].astype(float).to_numpy()
    ids = merged["context_row_id"].astype(str).tolist()
    draws = _day_matrix(generated_days, pipeline, ids, "trip_day").astype(int)

    observed_global = _weighted_share(observed, weights)
    global_errors: list[float] = []
    subgroup_errors: list[float] = []

    for replicate in range(REPLICATES):
        generated = draws[replicate]
        global_errors.append(
            abs(_weighted_share(generated, weights) - observed_global)
        )
        supported: list[float] = []
        for dimension in COND_DIMS:
            values = merged[dimension].astype(str).to_numpy()
            for group in sorted(set(values.tolist())):
                mask = values == group
                if int(mask.sum()) < 30:
                    continue
                obs = _weighted_share(observed[mask], weights[mask])
                gen = _weighted_share(generated[mask], weights[mask])
                supported.append(abs(gen - obs))
        if not supported:
            raise ValueError("No supported Participation conditional cells")
        subgroup_errors.append(max(supported))

    return {
        "M2-PART-01": float(np.mean(global_errors)),
        "M2-COND-01": float(np.mean(subgroup_errors)),
    }


def _build_count_universe(
    participation: pd.DataFrame,
    trip_count: pd.DataFrame,
    context: pd.DataFrame,
) -> pd.DataFrame:
    part = _merge_target_context(
        participation,
        context,
        target_name="participation",
        validate="one_to_one",
    )
    count = _merge_target_context(
        trip_count,
        context,
        target_name="trip_count",
        validate="one_to_one",
    )

    mobile_ids = set(
        part.loc[part["target_trip_day"].astype(int).eq(1), "context_row_id"].astype(str)
    )
    count_map = dict(
        zip(
            count["context_row_id"].astype(str),
            count["target_trip_count"].astype(int),
            strict=True,
        )
    )
    if not set(count_map) <= mobile_ids:
        raise ValueError("Trip Count targets must be observed mobile days")

    evaluable = part.loc[
        part["target_trip_day"].astype(int).eq(0)
        | part["context_row_id"].astype(str).isin(count_map)
    ].copy()
    observed = []
    for _, row in evaluable.iterrows():
        context_id = str(row["context_row_id"])
        if int(row["target_trip_day"]) == 0:
            observed.append(0)
        else:
            observed.append(int(count_map[context_id]))
    evaluable["observed_trip_count_full"] = observed
    if len(evaluable) != 442:
        raise ValueError("Unexpected Joint Trip Count evaluable person-days")
    return evaluable


def _count_tvd(
    observed: np.ndarray,
    generated: np.ndarray,
    weights: np.ndarray,
    *,
    mobile_only: bool,
) -> float:
    categories = list(range(1 if mobile_only else 0, 12)) + [12]
    obs_mask = observed > 0 if mobile_only else np.ones(len(observed), dtype=bool)
    gen_mask = generated > 0 if mobile_only else np.ones(len(generated), dtype=bool)

    obs = np.array(
        [
            np.sum(
                weights[
                    obs_mask
                    & ((observed == k) if k < 12 else (observed >= 12))
                ]
            )
            for k in categories
        ],
        dtype=float,
    )
    gen = np.array(
        [
            np.sum(
                weights[
                    gen_mask
                    & ((generated == k) if k < 12 else (generated >= 12))
                ]
            )
            for k in categories
        ],
        dtype=float,
    )
    if obs.sum() <= 0 or gen.sum() <= 0:
        raise ValueError("Trip Count TVD denominator is zero")
    obs /= obs.sum()
    gen /= gen.sum()
    return float(0.5 * np.abs(obs - gen).sum())


def trip_count_metrics(
    participation: pd.DataFrame,
    trip_count: pd.DataFrame,
    context: pd.DataFrame,
    generated_days: pd.DataFrame,
    pipeline: str,
) -> dict[str, float]:
    full = _build_count_universe(participation, trip_count, context)
    ids = full["context_row_id"].astype(str).tolist()
    draws = _day_matrix(generated_days, pipeline, ids, "trip_count").astype(int)
    observed = full["observed_trip_count_full"].astype(int).to_numpy()
    weights = full["fit_weight_P_GEW_target"].astype(float).to_numpy()
    mean_obs = float(np.average(observed, weights=weights))

    mean_errors: list[float] = []
    tvd_all: list[float] = []
    tvd_mobile: list[float] = []
    conditional: list[float] = []

    for replicate in range(REPLICATES):
        generated = draws[replicate]
        mean_errors.append(
            abs(float(np.average(generated, weights=weights)) - mean_obs)
        )
        tvd_all.append(_count_tvd(observed, generated, weights, mobile_only=False))
        tvd_mobile.append(_count_tvd(observed, generated, weights, mobile_only=True))

        supported: list[float] = []
        for dimension in COND_DIMS:
            values = full[dimension].astype(str).to_numpy()
            for group in sorted(set(values.tolist())):
                mask = values == group
                if int(mask.sum()) < 30:
                    continue
                obs = float(np.average(observed[mask], weights=weights[mask]))
                gen = float(np.average(generated[mask], weights=weights[mask]))
                supported.append(abs(gen - obs))
        if not supported:
            raise ValueError("No supported Trip Count conditional cells")
        conditional.append(max(supported))

    return {
        "M2-COUNT-01": float(np.mean(mean_errors)),
        "M2-COUNT-02": float(np.mean(tvd_all)),
        "M2-CHAIN-01": float(np.mean(tvd_mobile)),
        "M2-COND-02": float(np.mean(conditional)),
    }


def _chain_merged(
    chain_days: pd.DataFrame,
    chain_transitions: pd.DataFrame,
    context: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    days = _merge_target_context(
        chain_days,
        context,
        target_name="chain_days",
        validate="one_to_one",
    )
    transitions = _merge_target_context(
        chain_transitions,
        context,
        target_name="chain_transitions",
        validate="many_to_one",
    )
    if len(days) != 319 or len(transitions) != 1065:
        raise ValueError("Unexpected Joint Activity Chain CAL rows")
    return days, transitions


def chain_metrics(
    repo_root: Path,
    cfg: dict[str, Any],
    chain_days: pd.DataFrame,
    chain_transitions: pd.DataFrame,
    context: pd.DataFrame,
    generated_days: pd.DataFrame,
    pipeline: str,
    artifact_id: str,
) -> dict[str, float]:
    days, transitions = _chain_merged(chain_days, chain_transitions, context)
    ids = days["context_row_id"].astype(str).tolist()
    generated_k = _day_matrix(
        generated_days,
        pipeline,
        ids,
        "trip_count",
    ).astype(np.int16)

    purpose_cfg = {
        "precal_remediation": {
            "purpose_artifact": cfg["activity_chain"]["purpose_artifact"]["path"],
            "purpose_artifact_sha256": cfg["activity_chain"]["purpose_artifact"][
                "sha256"
            ],
        }
    }
    purpose = _load_purpose_artifact(repo_root, purpose_cfg)
    record = _record_by_id(repo_root, artifact_id)
    metrics, _, _ = _run_generated_guardrails(
        repo_root,
        [record],
        days,
        transitions,
        purpose,
        mode="PROPAGATED",
        generated_k=generated_k,
    )
    if len(metrics) != 1:
        raise ValueError("Unexpected Activity Chain metric row count")
    row = metrics.iloc[0]
    return {
        "M2-PURP-01": float(row["m2_purp_01_tvd_mean32"]),
        "M2-TRANS-01": float(row["m2_trans_01_tvd_mean32"]),
        "M2-RET-01": float(row["m2_ret_01_abs_error_mean32"]),
    }


def _context_weight_map(context: pd.DataFrame) -> dict[str, float]:
    weights = pd.to_numeric(context["fit_weight_P_GEW"], errors="raise").astype(float)
    if not np.isfinite(weights).all() or (weights <= 0).any():
        raise ValueError("Context P_GEW must be finite and positive")
    return dict(zip(context["row_id"].astype(str), weights, strict=True))


def _weighted_hour_tvd(
    observed_minutes: np.ndarray,
    observed_weights: np.ndarray,
    generated_minutes: np.ndarray,
    generated_weights: np.ndarray,
) -> float:
    observed = weighted_distribution(observed_minutes // 60, observed_weights)
    generated = weighted_distribution(generated_minutes // 60, generated_weights)
    return total_variation_distance(observed, generated)


def _circular_w1_minutes(
    observed: np.ndarray,
    observed_weights: np.ndarray,
    generated: np.ndarray,
    generated_weights: np.ndarray,
) -> float:
    obs = np.bincount(
        observed.astype(int),
        weights=observed_weights,
        minlength=1440,
    ).astype(float)
    gen = np.bincount(
        generated.astype(int),
        weights=generated_weights,
        minlength=1440,
    ).astype(float)
    if obs.sum() <= 0 or gen.sum() <= 0:
        raise ValueError("Circular W1 denominator is zero")
    obs /= obs.sum()
    gen /= gen.sum()
    cumulative = np.cumsum(obs - gen)[:-1]
    center = float(np.median(cumulative)) if len(cumulative) else 0.0
    return float(np.abs(cumulative - center).sum())


def time_metrics(
    time_trips: pd.DataFrame,
    context: pd.DataFrame,
    generated_trips: pd.DataFrame,
    pipeline: str,
) -> dict[str, float]:
    merged = _merge_time_context(time_trips, context)
    _validate_source_temporal_rows(merged)
    fixed_ids = set(merged["context_row_id"].astype(str))
    observed = merged["target_departure_clock_minute"].astype(int).to_numpy()
    observed_weights = merged["fit_weight_W_GEW"].astype(float).to_numpy()
    context_weights = _context_weight_map(context)

    tvds: list[float] = []
    circular: list[float] = []
    frame = generated_trips.loc[
        generated_trips["pipeline"].eq(pipeline)
        & generated_trips["row_id"].astype(str).isin(fixed_ids)
    ].copy()
    for replicate in range(REPLICATES):
        rep = frame.loc[frame["replicate_index"].astype(int).eq(replicate)]
        if rep.empty:
            raise ValueError("Generated Time denominator is zero")
        generated = rep["departure_clock_minute"].astype(int).to_numpy()
        weights = np.asarray(
            [context_weights[str(value)] for value in rep["row_id"]],
            dtype=float,
        )
        tvds.append(
            _weighted_hour_tvd(
                observed,
                observed_weights,
                generated,
                weights,
            )
        )
        circular.append(
            _circular_w1_minutes(
                observed,
                observed_weights,
                generated,
                weights,
            )
        )
    return {
        "M2-TIME-01": float(np.mean(tvds)),
        "TIME-CIRCULAR-W1": float(np.mean(circular)),
    }


def _distance_errors(
    target: pd.DataFrame,
    generated_trips: pd.DataFrame,
    context: pd.DataFrame,
    pipeline: str,
    *,
    target_column: str,
) -> tuple[float, dict[str, float]]:
    fixed_ids = set(target["context_row_id"].astype(str))
    observed = target[target_column].astype(float).to_numpy()
    observed_weights = target["fit_weight_W_GEW"].astype(float).to_numpy()
    context_weights = _context_weight_map(context)
    frame = generated_trips.loc[
        generated_trips["pipeline"].eq(pipeline)
        & generated_trips["row_id"].astype(str).isin(fixed_ids)
    ].copy()

    w1: list[float] = []
    mean_errors: list[float] = []
    quantile_errors = {"P50": [], "P90": [], "P95": []}
    targets = {
        "P50": weighted_quantile(observed, observed_weights, 0.50),
        "P90": weighted_quantile(observed, observed_weights, 0.90),
        "P95": weighted_quantile(observed, observed_weights, 0.95),
    }
    observed_mean = weighted_mean(observed, observed_weights)

    for replicate in range(REPLICATES):
        rep = frame.loc[frame["replicate_index"].astype(int).eq(replicate)]
        if rep.empty:
            raise ValueError("Generated Distance denominator is zero")
        generated = rep["distance_prior_km"].astype(float).to_numpy()
        generated_weights = np.asarray(
            [context_weights[str(value)] for value in rep["row_id"]],
            dtype=float,
        )
        w1.append(
            wasserstein_1d(
                observed,
                observed_weights,
                generated,
                generated_weights,
            )
        )
        mean_errors.append(
            abs(weighted_mean(generated, generated_weights) - observed_mean)
        )
        for name, q in (("P50", 0.50), ("P90", 0.90), ("P95", 0.95)):
            quantile_errors[name].append(
                abs(
                    weighted_quantile(generated, generated_weights, q)
                    - targets[name]
                )
            )

    summary = {
        "MEAN": float(np.mean(mean_errors)),
        **{
            name: float(np.mean(values))
            for name, values in quantile_errors.items()
        },
    }
    return float(np.mean(w1)), summary


def distance_metrics(
    raw: pd.DataFrame,
    sensitivity: pd.DataFrame,
    context: pd.DataFrame,
    generated_trips: pd.DataFrame,
    pipeline: str,
) -> dict[str, float]:
    if set(raw["distance_provenance"].astype(str)) != {"RAW_WEGKM"}:
        raise ValueError("Primary Distance provenance must be RAW_WEGKM")
    allowed = {"RAW_WEGKM", "SOURCE_IMPUTED_WEGKM"}
    if not set(sensitivity["distance_provenance"].astype(str)).issubset(allowed):
        raise ValueError("Unexpected Distance sensitivity provenance")

    primary, summary = _distance_errors(
        raw,
        generated_trips,
        context,
        pipeline,
        target_column="target_distance_prior_km",
    )
    sensitivity_w1, _ = _distance_errors(
        sensitivity,
        generated_trips,
        context,
        pipeline,
        target_column="target_distance_sensitivity_km",
    )
    return {
        "M2-DIST-01": primary,
        "DIST-MEAN": summary["MEAN"],
        "DIST-P50": summary["P50"],
        "DIST-P90": summary["P90"],
        "DIST-P95": summary["P95"],
        "M2-DIST-02": sensitivity_w1,
    }


def compute_pipeline_metrics(
    repo_root: Path,
    cfg: dict[str, Any],
    frames: dict[str, pd.DataFrame],
    generated_days: pd.DataFrame,
    generated_trips: pd.DataFrame,
    pipeline: str,
    chain_artifact_id: str,
) -> dict[str, float]:
    metrics: dict[str, float] = {}
    metrics.update(
        participation_metrics(
            frames["participation"],
            frames["person_day_context"],
            generated_days,
            pipeline,
        )
    )
    metrics.update(
        trip_count_metrics(
            frames["participation"],
            frames["trip_count"],
            frames["person_day_context"],
            generated_days,
            pipeline,
        )
    )
    metrics.update(
        chain_metrics(
            repo_root,
            cfg,
            frames["chain_days"],
            frames["chain_transitions"],
            frames["person_day_context"],
            generated_days,
            pipeline,
            chain_artifact_id,
        )
    )
    metrics.update(
        time_metrics(
            frames["time_trips"],
            frames["person_day_context"],
            generated_trips,
            pipeline,
        )
    )
    metrics.update(
        distance_metrics(
            frames["distance_raw"],
            frames["distance_expanded_sensitivity"],
            frames["person_day_context"],
            generated_trips,
            pipeline,
        )
    )
    return metrics


def build_joint_metric_rows(
    selected: dict[str, float],
    reference: dict[str, float],
) -> tuple[pd.DataFrame, bool]:
    matrix = pd.read_csv(METRIC_MATRIX)
    rows: list[dict[str, Any]] = []
    material_degradation = False

    for _, spec in matrix.iterrows():
        metric_id = str(spec["metric_id"])
        if metric_id not in selected or metric_id not in reference:
            raise ValueError(f"Missing Joint metric implementation: {metric_id}")
        selected_value = float(selected[metric_id])
        reference_value = float(reference[metric_id])
        worsening = selected_value - reference_value
        role = str(spec["decision_role"])
        raw_tolerance = spec["max_worsening"]
        tolerance = None if pd.isna(raw_tolerance) else float(raw_tolerance)

        if role == "REPORT_ONLY":
            passes = True
        else:
            if tolerance is None:
                raise ValueError(f"Decision metric lacks tolerance: {metric_id}")
            passes = worsening <= tolerance + 1e-15
            material_degradation = material_degradation or not passes

        rows.append(
            {
                "metric_id": metric_id,
                "scope": str(spec["scope"]),
                "statistic": str(spec["statistic"]),
                "decision_role": role,
                "selected_error": selected_value,
                "all_reference_error": reference_value,
                "selected_minus_reference_worsening": worsening,
                "max_worsening": tolerance,
                "unit": str(spec["unit"]),
                "gate_pass": bool(passes),
                "source_threshold": str(spec["source_threshold"]),
            }
        )

    return pd.DataFrame(rows), material_degradation


def selected_component_dominated() -> bool:
    witness = pd.read_csv(PRIMARY_WITNESS)
    if len(witness) != 5:
        raise ValueError("Expected exactly five primary dominance witnesses")
    return bool((witness["selected_minus_reference"].astype(float) > 0.0).any())


def _run_direct(
    repo_root: Path,
    staging: Path,
    config_path: Path,
    authorization: dict[str, Any],
) -> dict[str, Any]:
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    frames, input_validation, access = load_joint_cal_inputs(repo_root, cfg)

    registry = json.loads(JOINT_REGISTRY.read_text(encoding="utf-8"))
    selected_adapters, selected_validation = load_pipeline(
        repo_root,
        list(registry["selected_pipeline"]),
    )
    reference_adapters, reference_validation = load_pipeline(
        repo_root,
        list(registry["all_reference_pipeline"]),
    )

    context = frames["person_day_context"]
    selected_days_raw, selected_trips_raw, selected_violations = generate_pipeline(
        "SELECTED",
        selected_adapters,
        context,
        replicates=REPLICATES,
    )
    reference_days_raw, reference_trips_raw, reference_violations = generate_pipeline(
        "ALL_REFERENCE",
        reference_adapters,
        context,
        replicates=REPLICATES,
    )

    generated_days = pd.DataFrame(selected_days_raw + reference_days_raw)
    generated_trips = pd.DataFrame(selected_trips_raw + reference_trips_raw)
    artifact_validation = pd.DataFrame(
        [
            {"pipeline": "SELECTED", **row}
            for row in selected_validation
        ]
        + [
            {"pipeline": "ALL_REFERENCE", **row}
            for row in reference_validation
        ]
    )

    selected_metrics = compute_pipeline_metrics(
        repo_root,
        cfg,
        frames,
        generated_days,
        generated_trips,
        "SELECTED",
        str(cfg["activity_chain"]["selected_artifact"]),
    )
    reference_metrics = compute_pipeline_metrics(
        repo_root,
        cfg,
        frames,
        generated_days,
        generated_trips,
        "ALL_REFERENCE",
        str(cfg["activity_chain"]["reference_artifact"]),
    )
    metric_rows, material_degradation = build_joint_metric_rows(
        selected_metrics,
        reference_metrics,
    )

    structural = (
        int(selected_violations["structural"])
        + int(reference_violations["structural"])
        + int(selected_violations["distance"])
        + int(reference_violations["distance"])
    )
    temporal = (
        int(selected_violations["temporal"])
        + int(reference_violations["temporal"])
    )
    nofuture = (
        int(selected_violations["nofuture"])
        + int(reference_violations["nofuture"])
    )
    dominated = selected_component_dominated()
    manifests_frozen = bool(
        len(artifact_validation) == 10
        and artifact_validation["status"].eq("PASS").all()
    )

    gate = joint_cal_gate(
        JointGateInput(
            structural_invariant_violations=structural,
            temporal_invariant_violations=temporal,
            nofuture_violations=nofuture,
            selected_component_dominated=dominated,
            selected_pipeline_material_degradation=material_degradation,
            selected_artifact_manifests_frozen=manifests_frozen,
            post_cal_design_change=False,
        )
    )

    validation_checks = {
        "physical_cal_rows_6341": access["cal_rows_read_total_physical"] == 6341,
        "input_validation_all_pass": input_validation["status"].eq("PASS").all(),
        "pipeline_artifact_slots_10": len(artifact_validation) == 10,
        "pipeline_artifact_validation_all_pass": artifact_validation[
            "status"
        ].eq("PASS").all(),
        "replicates_32": REPLICATES == 32,
        "generated_days_nonempty": len(generated_days) > 0,
        "generated_trips_nonempty": len(generated_trips) > 0,
        "metric_matrix_complete": len(metric_rows) == len(pd.read_csv(METRIC_MATRIX)),
        "structural_invariants_zero": structural == 0,
        "temporal_invariants_zero": temporal == 0,
        "nofuture_invariants_zero": nofuture == 0,
        "candidate_selection_none": True,
        "test_rows_zero": True,
    }
    validation = pd.DataFrame(
        [
            {
                "check": name,
                "status": "PASS" if bool(value) else "FAIL",
            }
            for name, value in validation_checks.items()
        ]
    )
    if not validation["status"].eq("PASS").all():
        failed = validation.loc[validation["status"].eq("FAIL"), "check"].tolist()
        raise RuntimeError(f"Joint execution integrity validation failed: {failed}")

    input_validation.to_csv(staging / "input_validation.csv", index=False)
    artifact_validation.to_csv(
        staging / "pipeline_artifact_validation.csv",
        index=False,
    )
    generated_days.to_csv(staging / "generated_days.csv", index=False)
    generated_trips.to_csv(staging / "generated_trips.csv", index=False)
    metric_rows.to_csv(staging / "joint_metrics.csv", index=False)
    validation.to_csv(staging / "validation.csv", index=False)
    pd.DataFrame(columns=["issue_id", "severity", "detail"]).to_csv(
        staging / "issues.csv",
        index=False,
    )

    write_json(staging / "authorization_snapshot.json", authorization)
    write_json(
        staging / "contract_snapshot.json",
        {
            "phase": "F3.4g-2c",
            "joint_contract_sha256": sha256_file(
                repo_root
                / "configs/f3/f3_4g1_joint_cal_contract_freeze_v1.yaml"
            ),
            "metric_matrix_sha256": sha256_file(METRIC_MATRIX),
            "primary_witness_sha256": sha256_file(PRIMARY_WITNESS),
            "generated_trip_evaluation_weight": cfg["execution"][
                "generated_trip_evaluation_weight"
            ],
            "observed_trip_target_weight": cfg["execution"][
                "observed_trip_target_weight"
            ],
        },
    )
    write_json(staging / "cal_access_manifest.json", access)
    write_json(
        staging / "joint_gate.json",
        {
            "pass_gate": bool(gate.pass_gate),
            "reasons": list(gate.reasons),
            "test_eligible_by_joint_gate": bool(gate.test_open_authorized),
            "test_open_authorized": False,
            "formal_g2": gate.formal_g2,
            "selected_component_dominated": dominated,
            "selected_pipeline_material_degradation": material_degradation,
            "structural_invariant_violations": structural,
            "temporal_invariant_violations": temporal,
            "nofuture_violations": nofuture,
        },
    )
    write_json(
        staging / "environment.json",
        {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
    )

    implementation_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
    ).strip()
    manifest = {
        "phase": "F3.4g-2c",
        "component": "DGEN_JOINT_PIPELINE",
        "mode": "CONTROLLED_REAL_CAL",
        "status": "PASS",
        "implementation_commit": implementation_commit,
        "cal_files_opened": access["cal_files_opened"],
        "cal_rows_read_total_physical": access["cal_rows_read_total_physical"],
        "pipeline_artifact_slots": len(artifact_validation),
        "stochastic_replicates": REPLICATES,
        "generated_day_rows": len(generated_days),
        "generated_trip_rows": len(generated_trips),
        "candidate_selection": "NONE",
        "joint_gate_evaluated": True,
        "joint_gate_pass": bool(gate.pass_gate),
        "joint_gate_reasons": list(gate.reasons),
        "test_eligible_by_joint_gate": bool(gate.test_open_authorized),
        "test_open_authorized": False,
        "test_rows_read": 0,
        "formal_g2": "NOT_EVALUATED",
    }
    write_json(staging / "run_manifest.json", manifest)
    write_checksums(staging)
    return manifest


def run_controlled_joint_real_cal(
    repo_root: Path,
    output_dir: Path,
    config_path: Path,
    authorization_path: Path,
) -> dict[str, Any]:
    authorization = load_joint_real_cal_authorization(
        authorization_path,
        repo_root,
    )

    output = output_dir.expanduser().resolve()
    staging = Path(f"{output}.partial")
    if output.exists():
        raise FileExistsError(f"Final RunBundle already exists: {output}")
    if staging.exists():
        raise FileExistsError(f"Partial RunBundle already exists: {staging}")

    staging.mkdir(parents=True)
    try:
        manifest = _run_direct(
            repo_root,
            staging,
            config_path,
            authorization,
        )
        staging.rename(output)
        return manifest
    except Exception as exc:
        write_json(
            staging / "failure.json",
            {
                "phase": "F3.4g-2c",
                "status": "FAIL",
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
                "authorization_commit": authorization.get(
                    "authorized_implementation_commit"
                ),
                "same_authorization_rerun_allowed": False,
                "main_review_required": True,
            },
        )
        write_checksums(staging)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--authorization-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    manifest = run_controlled_joint_real_cal(
        REPO_ROOT,
        args.output_dir,
        args.config,
        args.authorization_json,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
