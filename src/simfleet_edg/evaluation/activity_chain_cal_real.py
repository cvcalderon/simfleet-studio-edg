"""Controlled real-CAL runner for F3.4d Activity Chain.

CAL I/O is permitted only after an external authorization bound to the exact
committed implementation HEAD has been validated. PRE-OPEN tests/verifiers must
never invoke :func:`run_controlled_activity_chain_cal` with a valid authorization.
"""

from __future__ import annotations

import gzip
import json
import platform
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from simfleet_edg.evaluation.activity_chain_adapter import ActivityChainAdapter
from simfleet_edg.evaluation.activity_chain_purpose_attribution import (
    attribute_generated_purpose,
)
from simfleet_edg.evaluation.cal_access_guard import PartitionAccess
from simfleet_edg.evaluation.cal_adapter_common import (
    ArtifactRecord,
    load_json,
    load_registry,
    sha256_file,
)
from simfleet_edg.evaluation.cal_bootstrap import (
    household_bootstrap_multipliers,
    percentile_interval,
)
from simfleet_edg.evaluation.cal_evidence import canonical_payload
from simfleet_edg.evaluation.cal_harness import evaluation_person_id, packed_draw_index
from simfleet_edg.evaluation.cal_metrics import (
    total_variation_distance,
    weighted_categorical_logloss,
    weighted_distribution,
    weighted_mean,
)
from simfleet_edg.evaluation.cal_protocol import (
    CAL_SCENARIO_ID,
    MASTER_SEED,
    bootstrap_seed,
    runtime_draw_seed,
)
from simfleet_edg.evaluation.cal_selection import (
    GridScore,
    choose_within_family,
    promotion_decision,
)
from simfleet_edg.evaluation.cal_state import propagated_chain_state
from simfleet_edg.evaluation.participation_adapter import ParticipationAdapter
from simfleet_edg.evaluation.trip_count_adapter import TripCountAdapter

COMPONENT = "DG_ACTIVITY_CHAIN"
PARTICIPATION_COMPONENT = "DG_PARTICIPATION"
TRIP_COUNT_COMPONENT = "DG_TRIP_COUNT"
UPSTREAM_PARTICIPATION_ID = "DG_PARTICIPATION::PART_A::PA1"
UPSTREAM_TRIP_COUNT_ID = "DG_TRIP_COUNT::COUNT_REF::REFERENCE"
REFERENCE_ID = "DG_ACTIVITY_CHAIN::CHAIN_REF::REFERENCE"
PURPOSE_PRIMITIVE_ID = "CHAIN_PURPOSE_ATTRIBUTION_V1"
REPLICATES = 32
BOOTSTRAPS = 1000
PRACTICAL_MARGIN = 0.01
ROLE_RANK = {
    "REFERENCE_BASELINE": 0,
    "CORE_CANDIDATE_A": 1,
    "CORE_CHALLENGER_B": 2,
}
FORBIDDEN_CHAIN_FEATURES = {
    "canonical_trip_purpose",
    "target_destination_activity",
    "source_trip_id",
    "fit_weight_W_GEW",
}


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo_root), *args],
        text=True,
    ).strip()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[dict[str, Any]] | pd.DataFrame) -> None:
    frame = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    frame.to_csv(path, index=False)


def _write_checksums(output_dir: Path) -> None:
    target = output_dir / "checksums.sha256"
    lines = [
        f"{sha256_file(path)}  {path.name}"
        for path in sorted(output_dir.iterdir())
        if path.is_file() and path.name != target.name
    ]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_authorization(path: Path, repo_root: Path) -> dict[str, Any]:
    """Validate external authorization before any CAL path is opened."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "phase": "F3.4d-2b",
        "component": COMPONENT,
        "real_activity_chain_cal_open_authorized": True,
        "candidate_artifacts": 6,
        "candidate_selection_at_entry": "NONE",
        "test_open_authorized": False,
        "next_component_authorized": False,
        "formal_g2": "NOT_EVALUATED",
    }
    for key, value in required.items():
        if payload.get(key) != value:
            raise PermissionError(f"Invalid execution authorization field {key}")
    current = _git(repo_root, "rev-parse", "HEAD")
    if payload.get("authorized_implementation_commit") != current:
        raise PermissionError("Authorization is not bound to current implementation commit")
    if set(payload.get("allowed_cal_files", [])) != {
        "person_day_context.csv",
        "chain_days.csv",
        "chain_transitions.csv",
    }:
        raise PermissionError("Authorization CAL file scope mismatch")
    if _git(repo_root, "status", "--porcelain"):
        raise PermissionError("Real CAL execution requires a clean worktree")
    if _git(repo_root, "branch", "--show-current") != "main":
        raise PermissionError("Real CAL execution requires main branch")
    if _git(repo_root, "rev-list", "--count", "origin/main..HEAD") != "0":
        raise PermissionError("Real CAL execution requires ahead=0")
    if _git(repo_root, "rev-list", "--count", "HEAD..origin/main") != "0":
        raise PermissionError("Real CAL execution requires behind=0")
    return payload


def _validate_input_file(path: Path, expected_sha: str, expected_rows: int) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    digest = sha256_file(path)
    if digest != expected_sha:
        raise ValueError(f"CAL input SHA mismatch for {path.name}")
    frame = pd.read_csv(path)
    if len(frame) != expected_rows:
        raise ValueError(
            f"CAL input row mismatch for {path.name}: {len(frame)} != {expected_rows}"
        )
    return frame


def _all_records(repo_root: Path) -> list[ArtifactRecord]:
    return load_registry(repo_root / "docs/F3_3_CANDIDATE_ARTIFACT_REGISTRY_v1.csv")


def _records(repo_root: Path) -> list[ArtifactRecord]:
    records = [r for r in _all_records(repo_root) if r.component == COMPONENT]
    if len(records) != 6:
        raise ValueError("Activity Chain candidate universe must contain 6 artifacts")
    if {r.train_state for r in records} != {"FITTED_TRAIN_ONLY_NOT_SELECTED"}:
        raise ValueError("Unexpected Activity Chain train_state")
    return sorted(records, key=lambda r: (ROLE_RANK[r.role], r.grid_id))


def _record_by_id(repo_root: Path, artifact_id: str) -> ArtifactRecord:
    found = [r for r in _all_records(repo_root) if r.artifact_id == artifact_id]
    if len(found) != 1:
        raise ValueError(f"Frozen artifact not found exactly once: {artifact_id}")
    if found[0].train_state != "FITTED_TRAIN_ONLY_NOT_SELECTED":
        raise ValueError(f"Unexpected registry train_state: {artifact_id}")
    return found[0]


def _merge_context(
    target: pd.DataFrame,
    context: pd.DataFrame,
    *,
    target_name: str,
) -> pd.DataFrame:
    merged = target.merge(
        context,
        left_on="context_row_id",
        right_on="row_id",
        how="left",
        validate="many_to_one",
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


def _validate_chain_structure(days: pd.DataFrame, transitions: pd.DataFrame) -> None:
    if days["context_row_id"].duplicated().any():
        raise ValueError("CAL chain_days context_row_id must be unique")
    keys = ["context_row_id", "trip_sequence_index"]
    if transitions[keys].duplicated().any():
        raise ValueError("CAL chain transition sequence keys must be unique")
    day_ids = set(days["context_row_id"].astype(str))
    transition_ids = set(transitions["context_row_id"].astype(str))
    if transition_ids != day_ids:
        raise ValueError("CAL chain transition/day context universes differ")

    by_context = {
        str(context_id): group.sort_values("trip_sequence_index")
        for context_id, group in transitions.groupby("context_row_id", sort=False)
    }
    for _, day in days.iterrows():
        context_id = str(day["context_row_id"])
        group = by_context[context_id]
        k = int(day["source_trip_count_analogue"])
        if k < 1 or len(group) != k:
            raise ValueError("Activity Chain requires exactly K observed transitions")
        seq = group["trip_sequence_index"].astype(int).tolist()
        if seq != list(range(1, k + 1)):
            raise ValueError("Observed chain sequence must be exactly 1..K")
        if int(group["source_trip_count_analogue"].nunique()) != 1:
            raise ValueError("Transition K must be constant within chain day")
        if int(group["source_trip_count_analogue"].iloc[0]) != k:
            raise ValueError("chain_days/chain_transitions K mismatch")
        if str(group["prefix_last_activity"].iloc[0]) != str(day["first_origin_activity"]):
            raise ValueError("Observed first-origin activity mismatch")
        if str(group["target_destination_activity"].iloc[-1]) != str(
            day["final_destination_activity"]
        ):
            raise ValueError("Observed final-destination activity mismatch")
        previous = str(day["first_origin_activity"])
        prefix: list[str] = [previous]
        for _, row in group.iterrows():
            if str(row["prefix_last_activity"]) != previous:
                raise ValueError("Observed chain prefix continuity failure")
            expected_second_last = "__START__" if len(prefix) == 1 else prefix[-2]
            if str(row["prefix_second_last_activity"]) != expected_second_last:
                raise ValueError("Observed second-last prefix continuity failure")
            previous = str(row["target_destination_activity"])
            prefix.append(previous)
        observed_return = int(str(previous) == "HOME")
        if observed_return != int(day["target_return_home"]):
            raise ValueError("Observed return-home target mismatch")


def load_and_validate_activity_chain_cal(
    repo_root: Path,
    cfg: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict[str, Any]], dict[str, Any]]:
    PartitionAccess(cal_authorized=True, test_authorized=False).require_cal()
    root = repo_root / cfg["cal_input"]["root"]
    loaded: dict[str, pd.DataFrame] = {}
    input_rows: list[dict[str, Any]] = []
    for key in ("person_day_context", "chain_days", "chain_transitions"):
        spec = cfg["cal_input"][key]
        path = root / spec["filename"]
        frame = _validate_input_file(path, str(spec["sha256"]), int(spec["expected_rows"]))
        loaded[key] = frame
        input_rows.append(
            {
                "filename": path.name,
                "sha256": sha256_file(path),
                "rows": len(frame),
                "status": "PASS",
            }
        )

    context = loaded["person_day_context"]
    days = loaded["chain_days"]
    transitions = loaded["chain_transitions"]
    required_context = {
        "row_id",
        "source_household_id",
        "source_person_id",
        "fit_weight_P_GEW",
    }
    required_days = {
        "context_row_id",
        "source_household_id",
        "source_person_id",
        "source_trip_count_analogue",
        "first_origin_activity",
        "final_destination_activity",
        "target_return_home",
        "day_weight_P_GEW",
    }
    required_transitions = {
        "context_row_id",
        "source_household_id",
        "source_person_id",
        "source_trip_id",
        "trip_sequence_index",
        "source_trip_count_analogue",
        "prefix_second_last_activity",
        "prefix_last_activity",
        "remaining_trips",
        "canonical_trip_purpose",
        "target_destination_activity",
        "fit_weight_W_GEW",
    }
    for name, frame, required in (
        ("context", context, required_context),
        ("chain_days", days, required_days),
        ("chain_transitions", transitions, required_transitions),
    ):
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"Missing {name} columns: {missing}")
    if context["row_id"].duplicated().any():
        raise ValueError("CAL context row_id must be unique")
    _validate_chain_structure(days, transitions)

    merged_days = _merge_context(days, context, target_name="chain_days")
    merged_transitions = _merge_context(
        transitions,
        context,
        target_name="chain_transitions",
    )
    if len(merged_days) != int(cfg["cal_input"]["expected_fixed_cohort_days"]):
        raise ValueError("Unexpected fixed Activity Chain cohort size")
    if len(merged_transitions) != int(
        cfg["cal_input"]["expected_isolated_transition_rows"]
    ):
        raise ValueError("Unexpected isolated Activity Chain transition rows")
    physical = sum(len(frame) for frame in loaded.values())
    if physical != int(cfg["cal_input"]["expected_physical_rows"]):
        raise ValueError("Unexpected physical CAL row count")

    access = {
        "cal_partition": "OPENED_AUTHORIZED_F3_4D2B",
        "cal_files_opened": [
            str((root / cfg["cal_input"][key]["filename"]).relative_to(repo_root))
            for key in ("person_day_context", "chain_days", "chain_transitions")
        ],
        "cal_file_rows": {
            cfg["cal_input"][key]["filename"]: len(loaded[key])
            for key in ("person_day_context", "chain_days", "chain_transitions")
        },
        "cal_rows_read_total_physical": physical,
        "cal_fixed_source_cohort_days": len(merged_days),
        "cal_isolated_transition_rows": len(merged_transitions),
        "test_partition": "SEALED",
        "test_files_opened": [],
        "test_rows_read": 0,
    }
    return merged_days, merged_transitions, context, input_rows, access


def _load_purpose_artifact(repo_root: Path, cfg: dict[str, Any]) -> dict[str, Any]:
    spec = cfg["precal_remediation"]
    path = repo_root / spec["purpose_artifact"]
    if sha256_file(path) != str(spec["purpose_artifact_sha256"]):
        raise ValueError("Purpose attribution artifact SHA mismatch")
    artifact = load_json(path)
    if artifact.get("primitive_id") != PURPOSE_PRIMITIVE_ID:
        raise ValueError("Unexpected purpose attribution primitive")
    if artifact.get("fit_partition") != "TRAIN":
        raise ValueError("Purpose attribution must remain TRAIN-fitted")
    if artifact.get("candidate_identity_in_rng_key") is not False:
        raise ValueError("Purpose attribution candidate identity must not enter RNG")
    if artifact.get("calibration_rows_read") != 0 or artifact.get("test_rows_read") != 0:
        raise ValueError("Purpose artifact boundary violation")
    return artifact


def _candidate_pmfs(
    repo_root: Path,
    records: list[ArtifactRecord],
    frame: pd.DataFrame,
) -> tuple[dict[str, np.ndarray], dict[str, list[str]], list[dict[str, Any]]]:
    pmfs: dict[str, np.ndarray] = {}
    supports: dict[str, list[str]] = {}
    validation: list[dict[str, Any]] = []
    for record in records:
        adapter = ActivityChainAdapter(repo_root, record)
        required = set()
        if record.candidate_id == "CHAIN_A":
            for level in adapter.model["levels"]:
                required.update(x for x in level["dimensions"] if x != "GLOBAL")
        elif record.candidate_id == "CHAIN_B":
            assert adapter.encoder is not None
            required.update(adapter.encoder.get("feature_columns", []))
        future = sorted(required & FORBIDDEN_CHAIN_FEATURES)
        if future:
            raise ValueError(f"NFI/feature violation for {record.artifact_id}: {future}")
        pmf = adapter.transition_pmf(frame)
        support = list(adapter.support)
        invalid = (
            pmf.ndim != 2
            or pmf.shape != (len(frame), len(support))
            or not np.isfinite(pmf).all()
            or (pmf < 0).any()
            or not np.allclose(pmf.sum(axis=1), 1.0, atol=1e-10)
        )
        if invalid:
            raise ValueError(f"Invalid Activity Chain PMF for {record.artifact_id}")
        pmfs[record.artifact_id] = pmf
        supports[record.artifact_id] = support
        validation.append(
            {
                "artifact_id": record.artifact_id,
                "candidate_id": record.candidate_id,
                "grid_id": record.grid_id,
                "role": record.role,
                "train_state": record.train_state,
                "model_sha256": record.model_sha256,
                "manifest_sha256": record.manifest_sha256,
                "pmf_rows": len(pmf),
                "support_size": len(support),
                "status": "PASS",
            }
        )
    return pmfs, supports, validation


def _observed_class_indices(frame: pd.DataFrame, support: list[str]) -> np.ndarray:
    lookup = {str(value): index for index, value in enumerate(support)}
    values = frame["target_destination_activity"].astype(str)
    unknown = sorted(set(values) - set(lookup))
    if unknown:
        raise ValueError(f"Observed next activity outside candidate support: {unknown}")
    return values.map(lookup).astype(int).to_numpy()


def _person_id_from_day(row: pd.Series) -> str:
    return evaluation_person_id(
        row["source_household_id_target"],
        row["source_person_id_target"],
    )


def _seed(person_id: str, replicate: int, component: str, event_index: int) -> int:
    return runtime_draw_seed(
        MASTER_SEED,
        CAL_SCENARIO_ID,
        person_id,
        component,
        packed_draw_index(replicate, event_index),
    )


def _static_state(row: pd.Series) -> dict[str, Any]:
    excluded = {
        "context_row_id",
        "source_household_id_target",
        "source_person_id_target",
        "source_trip_count_analogue",
        "first_origin_activity",
        "final_destination_activity",
        "target_return_home",
        "day_weight_P_GEW",
        "row_id",
        "source_household_id_context",
        "source_person_id_context",
        "fit_weight_P_GEW",
    }
    return {key: value for key, value in row.to_dict().items() if key not in excluded}


def _generate_chain(
    adapter: ActivityChainAdapter,
    day: pd.Series,
    *,
    trip_count: int,
    replicate: int,
    purpose_artifact: dict[str, Any],
) -> tuple[list[dict[str, Any]], str | None]:
    if trip_count < 0:
        raise ValueError("Generated trip count cannot be negative")
    if trip_count == 0:
        return [], None
    person_id = _person_id_from_day(day)
    static = _static_state(day)
    initial = adapter.sample_initial_activity(
        seed=_seed(person_id, replicate, COMPONENT, 0)
    )
    prefix = [initial]
    rows: list[dict[str, Any]] = []
    for trip_index in range(1, trip_count + 1):
        remaining = trip_count - trip_index
        state = propagated_chain_state(
            static,
            trip_count=trip_count,
            prefix=prefix,
            remaining_trips=remaining,
        )
        transition_seed = _seed(
            person_id,
            replicate,
            COMPONENT,
            2 * trip_index - 1,
        )
        sampled = adapter.sample_transition(pd.DataFrame([state]), seed=transition_seed)
        destination = str(sampled["next_activity"])
        purpose_state = {
            **state,
            "target_destination_activity": destination,
        }
        purpose_seed = _seed(
            person_id,
            replicate,
            COMPONENT,
            2 * trip_index,
        )
        u = float(np.random.default_rng(purpose_seed).random())
        purpose = attribute_generated_purpose(
            purpose_artifact,
            purpose_state,
            u=u,
        )
        rows.append(
            {
                "context_row_id": str(day["context_row_id"]),
                "source_household_id": str(day["source_household_id_target"]),
                "source_person_id": str(day["source_person_id_target"]),
                "evaluation_person_id": person_id,
                "trip_sequence_index": trip_index,
                "source_trip_count_analogue": trip_count,
                "prefix_second_last_activity": state["prefix_second_last_activity"],
                "prefix_last_activity": state["prefix_last_activity"],
                "remaining_trips": remaining,
                "generated_destination_activity": destination,
                "generated_purpose": purpose,
                "transition_seed_u64": transition_seed,
                "purpose_seed_u64": purpose_seed,
                "weight": float(day["day_weight_P_GEW"]),
            }
        )
        prefix.append(destination)
    if len(rows) != trip_count or len(prefix) != trip_count + 1:
        raise ValueError("Generated chain structural invariant failed")
    return rows, prefix[-1]


def _observed_surfaces(
    days: pd.DataFrame,
    transitions: pd.DataFrame,
) -> dict[str, Any]:
    purpose = weighted_distribution(
        transitions["canonical_trip_purpose"],
        transitions["fit_weight_W_GEW"],
    )
    transition_categories = (
        transitions["prefix_last_activity"].astype(str)
        + "->"
        + transitions["target_destination_activity"].astype(str)
    )
    transition = weighted_distribution(
        transition_categories,
        transitions["fit_weight_W_GEW"],
    )
    return_home_share = weighted_mean(
        days["target_return_home"].astype(int),
        days["day_weight_P_GEW"],
    )
    return {
        "purpose_distribution": purpose,
        "transition_distribution": transition,
        "return_home_share": return_home_share,
    }


def _metrics_from_generated(
    observed: dict[str, Any],
    generated_rows: list[dict[str, Any]],
    day_results: list[dict[str, Any]],
) -> dict[str, float]:
    if not generated_rows:
        raise ValueError("Generated transition denominator is zero")
    generated = pd.DataFrame(generated_rows)
    purpose = weighted_distribution(generated["generated_purpose"], generated["weight"])
    transitions = weighted_distribution(
        generated["prefix_last_activity"].astype(str)
        + "->"
        + generated["generated_destination_activity"].astype(str),
        generated["weight"],
    )
    mobile = pd.DataFrame(day_results)
    mobile = mobile[mobile["generated_trip_count"].astype(int) > 0]
    if mobile.empty:
        raise ValueError("Generated functional-mobile-day denominator is zero")
    return_share = weighted_mean(
        mobile["generated_return_home"].astype(int),
        mobile["weight"],
    )
    return {
        "m2_purp_01_tvd": total_variation_distance(
            observed["purpose_distribution"], purpose
        ),
        "m2_trans_01_tvd": total_variation_distance(
            observed["transition_distribution"], transitions
        ),
        "m2_ret_01_abs_error": abs(
            float(return_share) - float(observed["return_home_share"])
        ),
    }


def _run_generated_guardrails(
    repo_root: Path,
    records: list[ArtifactRecord],
    days: pd.DataFrame,
    transitions: pd.DataFrame,
    purpose_artifact: dict[str, Any],
    *,
    mode: str,
    generated_k: np.ndarray | None = None,
) -> tuple[pd.DataFrame, dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    if mode not in {"ISOLATED", "PROPAGATED"}:
        raise ValueError(mode)
    if generated_k is not None and generated_k.shape != (REPLICATES, len(days)):
        raise ValueError("Generated K shape mismatch")
    observed = _observed_surfaces(days, transitions)
    metric_rows: list[dict[str, Any]] = []
    all_transition_rows: dict[str, list[dict[str, Any]]] = {}
    all_day_rows: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        adapter = ActivityChainAdapter(repo_root, record)
        per_rep: list[dict[str, float]] = []
        artifact_transitions: list[dict[str, Any]] = []
        artifact_days: list[dict[str, Any]] = []
        for replicate in range(REPLICATES):
            rep_transitions: list[dict[str, Any]] = []
            rep_days: list[dict[str, Any]] = []
            for day_index, (_, day) in enumerate(days.iterrows()):
                k = (
                    int(day["source_trip_count_analogue"])
                    if generated_k is None
                    else int(generated_k[replicate, day_index])
                )
                chain_rows, final_activity = _generate_chain(
                    adapter,
                    day,
                    trip_count=k,
                    replicate=replicate,
                    purpose_artifact=purpose_artifact,
                )
                for row in chain_rows:
                    row.update(
                        {
                            "artifact_id": record.artifact_id,
                            "candidate_id": record.candidate_id,
                            "grid_id": record.grid_id,
                            "role": record.role,
                            "evaluation_mode": mode,
                            "replicate_id": replicate,
                        }
                    )
                rep_transitions.extend(chain_rows)
                rep_days.append(
                    {
                        "artifact_id": record.artifact_id,
                        "evaluation_mode": mode,
                        "replicate_id": replicate,
                        "context_row_id": str(day["context_row_id"]),
                        "source_household_id": str(day["source_household_id_target"]),
                        "source_person_id": str(day["source_person_id_target"]),
                        "generated_trip_count": k,
                        "generated_return_home": int(k > 0 and final_activity == "HOME"),
                        "weight": float(day["day_weight_P_GEW"]),
                    }
                )
            metrics = _metrics_from_generated(observed, rep_transitions, rep_days)
            per_rep.append(metrics)
            artifact_transitions.extend(rep_transitions)
            artifact_days.extend(rep_days)
        metric_rows.append(
            {
                "artifact_id": record.artifact_id,
                "m2_purp_01_tvd_mean32": float(
                    np.mean([x["m2_purp_01_tvd"] for x in per_rep])
                ),
                "m2_trans_01_tvd_mean32": float(
                    np.mean([x["m2_trans_01_tvd"] for x in per_rep])
                ),
                "m2_ret_01_abs_error_mean32": float(
                    np.mean([x["m2_ret_01_abs_error"] for x in per_rep])
                ),
            }
        )
        all_transition_rows[record.artifact_id] = artifact_transitions
        all_day_rows[record.artifact_id] = artifact_days
    return pd.DataFrame(metric_rows), all_transition_rows, all_day_rows


def _compare_guardrails(
    incumbent: dict[str, float],
    challenger: dict[str, float],
) -> tuple[bool, dict[str, Any]]:
    specs = (
        ("m2_purp_01_tvd_mean32", 0.005),
        ("m2_trans_01_tvd_mean32", 0.005),
        ("m2_ret_01_abs_error_mean32", 0.01),
    )
    row: dict[str, Any] = {}
    passed = True
    for metric, tolerance in specs:
        worsening = float(challenger[metric] - incumbent[metric])
        row[f"{metric}_worsening"] = worsening
        row[f"{metric}_tolerance"] = tolerance
        passed = passed and worsening <= tolerance + 1e-15
    row["guardrails_pass"] = passed
    return passed, row


def _bootstrap_improvement(
    transitions: pd.DataFrame,
    incumbent_pmf: np.ndarray,
    incumbent_support: list[str],
    challenger_pmf: np.ndarray,
    challenger_support: list[str],
    incumbent_id: str,
    challenger_id: str,
) -> dict[str, Any]:
    if incumbent_support != challenger_support:
        raise ValueError("Activity Chain supports differ across compared candidates")
    y = _observed_class_indices(transitions, incumbent_support)
    base_weight = transitions["fit_weight_W_GEW"].astype(float).to_numpy()
    multipliers = household_bootstrap_multipliers(
        transitions["source_household_id_target"],
        replicates=BOOTSTRAPS,
        seed=bootstrap_seed(MASTER_SEED, COMPONENT, incumbent_id, challenger_id),
    )
    differences = np.empty(BOOTSTRAPS, dtype=float)
    for index, multiplier in enumerate(multipliers):
        weight = base_weight * multiplier
        if weight.sum() <= 0:
            raise ValueError("Bootstrap removed all Activity Chain rows")
        incumbent = weighted_categorical_logloss(y, incumbent_pmf, weight)
        challenger = weighted_categorical_logloss(y, challenger_pmf, weight)
        differences[index] = incumbent - challenger
    interval = percentile_interval(differences, confidence_level=0.95)
    return {
        "incumbent_artifact_id": incumbent_id,
        "challenger_artifact_id": challenger_id,
        "bootstrap_replicates": BOOTSTRAPS,
        "ci_lower": interval.lower,
        "ci_median": interval.median,
        "ci_upper": interval.upper,
    }


def _candidate_score(
    record: ArtifactRecord,
    primary_by_id: dict[str, float],
    guardrails_pass: bool,
) -> GridScore:
    return GridScore(
        artifact_id=record.artifact_id,
        candidate_id=record.candidate_id,
        grid_id=record.grid_id,
        role=record.role,
        primary_metric=float(primary_by_id[record.artifact_id]),
        hard_pass=True,
        guardrails_pass=bool(guardrails_pass),
    )


def _upstream_generated_k(
    repo_root: Path,
    days: pd.DataFrame,
) -> tuple[np.ndarray, dict[str, Any]]:
    part_record = _record_by_id(repo_root, UPSTREAM_PARTICIPATION_ID)
    count_record = _record_by_id(repo_root, UPSTREAM_TRIP_COUNT_ID)
    part = ParticipationAdapter(repo_root, part_record)
    count = TripCountAdapter(repo_root, count_record)
    probability = part.probabilities(days)
    pmf = count.pmf(days)
    support = np.asarray(count.support, dtype=int)
    if len(probability) != len(days) or pmf.shape != (len(days), len(support)):
        raise ValueError("Upstream propagated shape mismatch")
    cdf = np.cumsum(pmf, axis=1)
    out = np.zeros((REPLICATES, len(days)), dtype=int)
    for replicate in range(REPLICATES):
        for row_index, (_, day) in enumerate(days.iterrows()):
            person_id = _person_id_from_day(day)
            part_u = np.random.default_rng(
                _seed(person_id, replicate, PARTICIPATION_COMPONENT, 0)
            ).random()
            if part_u >= float(probability[row_index]):
                continue
            count_u = np.random.default_rng(
                _seed(person_id, replicate, TRIP_COUNT_COMPONENT, 0)
            ).random()
            index = int(np.sum(count_u > cdf[row_index]))
            index = min(index, len(support) - 1)
            out[replicate, row_index] = int(support[index])
    return out, {
        "participation_artifact_id": UPSTREAM_PARTICIPATION_ID,
        "participation_state": "MAIN_FROZEN",
        "trip_count_artifact_id": UPSTREAM_TRIP_COUNT_ID,
        "trip_count_state": "MAIN_FROZEN",
        "fixed_source_cohort_days": len(days),
        "cohort_reselected": False,
    }


def _run_controlled_activity_chain_cal_direct(
    repo_root: Path,
    output_dir: Path,
    config_path: Path,
    authorization_path: Path,
    *,
    write_stochastic_evidence: bool = True,
) -> dict[str, Any]:
    started = time.perf_counter()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if config.get("phase") != "F3.4d-2b":
        raise ValueError("Unexpected Activity Chain real-CAL implementation contract")

    # Authorization MUST succeed before CAL I/O or staging directory creation.
    authorization = load_authorization(authorization_path, repo_root)
    if output_dir.exists():
        raise FileExistsError(f"RunBundle output already exists: {output_dir}")
    output_dir.mkdir(parents=True)

    days, transitions, _, input_rows, access = load_and_validate_activity_chain_cal(
        repo_root,
        config,
    )
    records = _records(repo_root)
    purpose_artifact = _load_purpose_artifact(repo_root, config)
    pmfs, supports, artifact_validation = _candidate_pmfs(
        repo_root,
        records,
        transitions,
    )

    primary_rows: list[dict[str, Any]] = []
    primary_by_id: dict[str, float] = {}
    weights = transitions["fit_weight_W_GEW"].astype(float).to_numpy()
    for record in records:
        y = _observed_class_indices(transitions, supports[record.artifact_id])
        value = weighted_categorical_logloss(y, pmfs[record.artifact_id], weights)
        primary_by_id[record.artifact_id] = value
        primary_rows.append(
            {
                "artifact_id": record.artifact_id,
                "candidate_id": record.candidate_id,
                "grid_id": record.grid_id,
                "role": record.role,
                "primary_metric": "WEIGHTED_NEXT_ACTIVITY_LOG_LOSS",
                "value": value,
                "hard_pass": True,
            }
        )
    primary_frame = pd.DataFrame(primary_rows)

    isolated_metrics, isolated_generated, _isolated_day_results = _run_generated_guardrails(
        repo_root,
        records,
        days,
        transitions,
        purpose_artifact,
        mode="ISOLATED",
    )
    guard_by_id = isolated_metrics.set_index("artifact_id").to_dict(orient="index")
    record_map = {record.artifact_id: record for record in records}
    reference = record_map[REFERENCE_ID]
    pair_guardrails: list[dict[str, Any]] = []

    def compare(record: ArtifactRecord, incumbent: ArtifactRecord) -> bool:
        passed, row = _compare_guardrails(
            guard_by_id[incumbent.artifact_id],
            guard_by_id[record.artifact_id],
        )
        pair_guardrails.append(
            {
                "incumbent_artifact_id": incumbent.artifact_id,
                "challenger_artifact_id": record.artifact_id,
                **row,
            }
        )
        return passed

    grid_rows: list[dict[str, Any]] = []
    bootstrap_rows: list[dict[str, Any]] = []
    promotion_rows: list[dict[str, Any]] = []
    incumbent = reference

    a_records = [r for r in records if r.role == "CORE_CANDIDATE_A"]
    a_scores = [_candidate_score(r, primary_by_id, compare(r, reference)) for r in a_records]
    best_a = choose_within_family(a_scores)
    for score in a_scores:
        grid_rows.append(
            {
                **asdict(score),
                "family": "A",
                "selected_within_family": bool(
                    best_a and score.artifact_id == best_a.artifact_id
                ),
            }
        )
    if best_a is not None:
        boot = _bootstrap_improvement(
            transitions,
            pmfs[reference.artifact_id],
            supports[reference.artifact_id],
            pmfs[best_a.artifact_id],
            supports[best_a.artifact_id],
            reference.artifact_id,
            best_a.artifact_id,
        )
        bootstrap_rows.append(boot)
        decision = promotion_decision(
            _candidate_score(reference, primary_by_id, True),
            best_a,
            practical_margin=PRACTICAL_MARGIN,
            bootstrap_ci_lower=float(boot["ci_lower"]),
            bootstrap_ci_upper=float(boot["ci_upper"]),
        )
        promotion_rows.append(
            {
                **asdict(decision),
                "reasons": ";".join(decision.reasons),
                "stage": "REF_TO_A",
            }
        )
        if decision.promoted:
            incumbent = record_map[best_a.artifact_id]

    b_records = [r for r in records if r.role == "CORE_CHALLENGER_B"]
    b_scores = [_candidate_score(r, primary_by_id, compare(r, incumbent)) for r in b_records]
    best_b = choose_within_family(b_scores)
    for score in b_scores:
        grid_rows.append(
            {
                **asdict(score),
                "family": "B",
                "selected_within_family": bool(
                    best_b and score.artifact_id == best_b.artifact_id
                ),
            }
        )
    if best_b is not None:
        boot = _bootstrap_improvement(
            transitions,
            pmfs[incumbent.artifact_id],
            supports[incumbent.artifact_id],
            pmfs[best_b.artifact_id],
            supports[best_b.artifact_id],
            incumbent.artifact_id,
            best_b.artifact_id,
        )
        bootstrap_rows.append(boot)
        decision = promotion_decision(
            _candidate_score(incumbent, primary_by_id, True),
            best_b,
            practical_margin=PRACTICAL_MARGIN,
            bootstrap_ci_lower=float(boot["ci_lower"]),
            bootstrap_ci_upper=float(boot["ci_upper"]),
        )
        promotion_rows.append(
            {
                **asdict(decision),
                "reasons": ";".join(decision.reasons),
                "stage": "INCUMBENT_TO_B",
            }
        )
        if decision.promoted:
            incumbent = record_map[best_b.artifact_id]

    generated_k, upstream_snapshot = _upstream_generated_k(repo_root, days)
    propagated_records = [reference]
    if incumbent.artifact_id != reference.artifact_id:
        propagated_records.append(incumbent)
    propagated_metrics, propagated_generated, _propagated_day_results = _run_generated_guardrails(
        repo_root,
        propagated_records,
        days,
        transitions,
        purpose_artifact,
        mode="PROPAGATED",
        generated_k=generated_k,
    )
    prop_by_id = propagated_metrics.set_index("artifact_id").to_dict(orient="index")
    propagated_pass, propagated_row = _compare_guardrails(
        prop_by_id[reference.artifact_id],
        prop_by_id[incumbent.artifact_id],
    )
    propagated_guardrail_rows = [
        {
            "incumbent_artifact_id": reference.artifact_id,
            "challenger_artifact_id": incumbent.artifact_id,
            **propagated_row,
        }
    ]

    selected = {
        "status": (
            "PROPOSED_BY_FROZEN_CAL_RULES_AWAITING_MAIN_FREEZE"
            if propagated_pass
            else "BLOCKED_PROPAGATED_GUARDRAIL_RETURN_TO_MAIN"
        ),
        "base_artifact_id": incumbent.artifact_id,
        "proposed_selected_artifact_id": incumbent.artifact_id if propagated_pass else None,
        "candidate_id": incumbent.candidate_id,
        "grid_id": incumbent.grid_id,
        "role": incumbent.role,
        "isolated_selection_complete": True,
        "propagated_guardrails_pass": propagated_pass,
        "authorized_for_downstream": False,
        "next_component_authorized": False,
    }

    _write_csv(output_dir / "input_hash_validation.csv", input_rows)
    _write_csv(output_dir / "candidate_artifact_validation.csv", artifact_validation)
    _write_csv(output_dir / "primary_metrics.csv", primary_frame)
    _write_csv(output_dir / "isolated_guardrail_candidate_metrics.csv", isolated_metrics)
    _write_csv(output_dir / "isolated_guardrails.csv", pair_guardrails)
    _write_csv(output_dir / "bootstrap_intervals.csv", bootstrap_rows)
    _write_csv(output_dir / "grid_selection.csv", grid_rows)
    _write_csv(output_dir / "promotion_decisions.csv", promotion_rows)
    _write_csv(output_dir / "propagated_guardrail_candidate_metrics.csv", propagated_metrics)
    _write_csv(output_dir / "propagated_guardrails.csv", propagated_guardrail_rows)
    _write_json(output_dir / "upstream_selection_snapshot.json", upstream_snapshot)
    _write_json(
        output_dir / "purpose_attribution_snapshot.json",
        {
            "primitive_id": PURPOSE_PRIMITIVE_ID,
            "artifact_path": config["precal_remediation"]["purpose_artifact"],
            "artifact_sha256": config["precal_remediation"]["purpose_artifact_sha256"],
            "candidate_scope": "SHARED_IDENTICAL_PRIMITIVE_FOR_ALL_SIX_ACTIVITY_CHAIN_CANDIDATES",
            "candidate_identity_in_rng_key": False,
        },
    )
    _write_json(output_dir / "selected_component_artifact.json", selected)
    _write_json(output_dir / "cal_access_manifest.json", access)
    _write_json(output_dir / "execution_authorization_snapshot.json", authorization)
    (output_dir / "execution_contract_snapshot.yaml").write_bytes(config_path.read_bytes())
    _write_json(
        output_dir / "environment.json",
        {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
    )

    evidence_rows = 0
    if write_stochastic_evidence:
        evidence_path = output_dir / "stochastic_evidence.csv.gz"
        with gzip.open(evidence_path, "wt", encoding="utf-8", newline="") as handle:
            header_written = False
            for mode, source in (
                ("ISOLATED", isolated_generated),
                ("PROPAGATED", propagated_generated),
            ):
                for artifact_id, rows in source.items():
                    record = record_map[artifact_id]
                    if not rows:
                        continue
                    frame = pd.DataFrame(rows)
                    evidence = pd.DataFrame(
                        {
                            "component": COMPONENT,
                            "artifact_id": artifact_id,
                            "candidate_id": record.candidate_id,
                            "grid_id": record.grid_id,
                            "role": record.role,
                            "evaluation_mode": mode,
                            "replicate_id": frame["replicate_id"],
                            "evaluation_person_id": frame["evaluation_person_id"],
                            "source_household_id": frame["source_household_id"],
                            "event_index": frame["trip_sequence_index"],
                            "draw_index": [
                                packed_draw_index(int(rep), 2 * int(event) - 1)
                                for rep, event in zip(
                                    frame["replicate_id"],
                                    frame["trip_sequence_index"],
                                )
                            ],
                            "seed_u64": frame["transition_seed_u64"],
                            "weight": frame["weight"],
                            "observed_json": [canonical_payload({})] * len(frame),
                            "generated_json": [
                                canonical_payload(
                                    {
                                        "destination_activity": destination,
                                        "purpose": purpose,
                                    }
                                )
                                for destination, purpose in zip(
                                    frame["generated_destination_activity"],
                                    frame["generated_purpose"],
                                )
                            ],
                        }
                    )
                    evidence.to_csv(handle, index=False, header=not header_written)
                    header_written = True
                    evidence_rows += len(evidence)

    _write_json(
        output_dir / "evidence_manifest.json",
        {
            "schema": "F3_3C_STANDARD_EVIDENCE_V1_COMPATIBLE_ACTIVITY_CHAIN",
            "rows": evidence_rows,
            "isolated_candidate_artifacts": len(records),
            "propagated_artifacts": len(propagated_records),
            "fixed_source_cohort_days": len(days),
            "common_random_numbers": True,
            "replicates": REPLICATES,
        },
    )
    _write_csv(
        output_dir / "validation.csv",
        [
            {"check": "cal_input_hashes_exact", "status": "PASS"},
            {"check": "cal_expected_rows_exact", "status": "PASS"},
            {"check": "activity_chain_artifacts_exact_6", "status": "PASS"},
            {"check": "purpose_attribution_train_frozen", "status": "PASS"},
            {"check": "upstream_pa1_main_frozen", "status": "PASS"},
            {"check": "upstream_count_ref_main_frozen", "status": "PASS"},
            {"check": "isolated_primary_logloss", "status": "PASS"},
            {"check": "common_random_numbers_32", "status": "PASS"},
            {"check": "household_bootstrap_1000", "status": "PASS"},
            {"check": "fixed_propagated_cohort_319", "status": "PASS"},
            {"check": "propagated_check_executed", "status": "PASS"},
            {"check": "test_rows_read_zero", "status": "PASS"},
            {"check": "downstream_not_authorized", "status": "PASS"},
        ],
    )
    _write_csv(
        output_dir / "issues.csv",
        pd.DataFrame(columns=["issue_id", "severity", "detail"]),
    )
    _write_json(
        output_dir / "performance.json",
        {
            "wall_seconds": time.perf_counter() - started,
            "cal_physical_rows_read": access["cal_rows_read_total_physical"],
            "isolated_transition_rows": len(transitions),
            "fixed_source_cohort_days": len(days),
            "candidate_artifacts": len(records),
            "stochastic_replicates": REPLICATES,
            "bootstrap_replicates": BOOTSTRAPS,
            "stochastic_evidence_rows": evidence_rows,
        },
    )
    manifest = {
        "phase": "F3.4d-2b",
        "component": COMPONENT,
        "status": "PASS",
        "execution_mode": "CONTROLLED_REAL_CAL",
        "candidate_artifacts": 6,
        "candidate_selection_state": selected["status"],
        "proposed_selected_artifact_id": selected["proposed_selected_artifact_id"],
        "propagated_guardrails_pass": propagated_pass,
        "cal_files_opened": access["cal_files_opened"],
        "cal_rows_read_total_physical": access["cal_rows_read_total_physical"],
        "cal_fixed_source_cohort_days": access["cal_fixed_source_cohort_days"],
        "cal_isolated_transition_rows": access["cal_isolated_transition_rows"],
        "test_rows_read": 0,
        "next_component_authorized": False,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
        "implementation_commit": _git(repo_root, "rev-parse", "HEAD"),
    }
    _write_json(output_dir / "run_manifest.json", manifest)
    _write_checksums(output_dir)
    return manifest


def run_controlled_activity_chain_cal(
    repo_root: Path,
    output_dir: Path,
    config_path: Path,
    authorization_path: Path,
    *,
    write_stochastic_evidence: bool = True,
) -> dict[str, Any]:
    """Run official Activity Chain CAL atomically and preserve failure evidence."""
    if output_dir.exists():
        raise FileExistsError(f"RunBundle output already exists: {output_dir}")
    staging = output_dir.with_name(f"{output_dir.name}.partial")
    if staging.exists():
        raise FileExistsError(f"Partial RunBundle already exists: {staging}")
    try:
        manifest = _run_controlled_activity_chain_cal_direct(
            repo_root,
            staging,
            config_path,
            authorization_path,
            write_stochastic_evidence=write_stochastic_evidence,
        )
        staging.rename(output_dir)
        return manifest
    except Exception as exc:
        if staging.exists():
            _write_json(
                staging / "failure.json",
                {
                    "status": "FAIL",
                    "phase": "F3.4d-2b",
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                    "cal_read_may_have_occurred": True,
                    "test_open_authorized": False,
                    "next_component_authorized": False,
                },
            )
            _write_checksums(staging)
        raise
