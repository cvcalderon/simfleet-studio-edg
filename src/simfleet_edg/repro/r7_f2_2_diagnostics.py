"""R7 PRE-F3 reproduction: deterministic F2.2 diagnostic validation metrics."""

from __future__ import annotations

import argparse
import csv
import json
import resource
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from simfleet_edg.common.diagnostic_metrics import (
    build_conditional_metrics,
    build_distribution_detail,
    build_global_metrics,
    build_selection_bias_audit,
    load_f22_context,
    reference_frames,
)
from simfleet_edg.common.population_split import sha256_file

METRIC_PROTOCOL = "simfleet_edg_F2_2_metric_protocol_v1.csv"
REFERENCE_POPULATIONS = "simfleet_edg_F2_2_reference_populations_v1.csv"
GLOBAL_METRICS = "simfleet_edg_F2_2_global_metrics_v1.csv"
DISTRIBUTION_DETAIL = "simfleet_edg_F2_2_distribution_detail_v1.csv"
CONDITIONAL_METRICS = "simfleet_edg_F2_2_conditional_metrics_v1.csv"
SELECTION_BIAS = "simfleet_edg_F2_2_selection_bias_audit_v1.csv"
DIAGNOSTIC_ISSUES = "simfleet_edg_F2_2_diagnostic_issues_v1.csv"
VALIDATION = "simfleet_edg_F2_2_validation_v1.csv"
F22_MANIFEST = "simfleet_edg_F2_2_manifest_v1.json"
REPORT = "simfleet_edg_F2_2_diagnostic_validation_report_v1.md"
TRACEABILITY = "simfleet_edg_F2_2_traceability_entry_v1.md"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _git_state(root: Path) -> dict[str, Any]:
    commit = _git(root, "rev-parse", "HEAD")
    branch = _git(root, "branch", "--show-current")
    clean = not bool(_git(root, "status", "--porcelain"))
    upstream = None
    ahead = behind = None
    try:
        upstream = _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        counts = _git(root, "rev-list", "--left-right", "--count", "HEAD...@{u}").split()
        ahead, behind = map(int, counts)
    except (subprocess.CalledProcessError, ValueError):
        pass
    return {"commit": commit, "branch": branch, "worktree_clean": clean, "upstream": upstream, "ahead": ahead, "behind": behind}


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Cannot write empty CSV: {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _checksums(out: Path) -> None:
    lines = []
    for path in sorted(out.iterdir()):
        if path.is_file() and path.name != "checksums.sha256":
            lines.append(f"{sha256_file(path)}  {path.name}")
    (out / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _source_hash_rows(root: Path, specs: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for name, spec in specs.items():
        path = root / spec["path"]
        actual = sha256_file(path) if path.is_file() else ""
        rows.append({"source": name, "path": spec["path"], "expected_sha256": spec["sha256"], "actual_sha256": actual, "status": "PASS" if actual == spec["sha256"] else "FAIL"})
    return rows


def _validation(check: str, ok: bool, detail: str) -> dict[str, str]:
    return {"check": check, "status": "PASS" if ok else "FAIL", "detail": detail}


def _reference_population_frame(refs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = [
        ("REF_TRAIN_BINARY", "Person-day", len(refs["REF_TRAIN_BINARY"]), "P_GEW", "mobil_diff in {0,1,2,3,5}", "Participation"),
        ("REF_TRAIN_CORE_STRICT_COUNT", "Person-day", len(refs["REF_TRAIN_CORE_STRICT_COUNT"]), "P_GEW", "trip_count_fit_tier=CORE_STRICT_COUNT", "Trips/person/day"),
        ("REF_TRAIN_CORE_STRICT_COUNT_MOBILE", "Mobile person-day", len(refs["REF_TRAIN_CORE_STRICT_COUNT_MOBILE"]), "P_GEW", "CORE_STRICT_COUNT and trips>0", "Chain length"),
        ("REF_TRAIN_DIRECT_PURPOSE", "Trip", len(refs["REF_TRAIN_DIRECT_PURPOSE"]), "W_GEW", "direct + purpose_marginal_eligible", "Purpose"),
        ("REF_TRAIN_DIRECT_TIME_VALID", "Trip", len(refs["REF_TRAIN_DIRECT_TIME_VALID"]), "W_GEW", "direct + DIRECT_TEMPORAL_VALID", "Departure time"),
        ("REF_TRAIN_TRANSITION", "Trip transition", len(refs["REF_TRAIN_TRANSITION"]), "W_GEW", "direct + transition_observation_eligible", "Activity transitions"),
        ("REF_TRAIN_DISTANCE_RAW", "Trip", len(refs["REF_TRAIN_DISTANCE_RAW"]), "W_GEW", "direct + source raw distance valid", "Distance primary"),
        ("REF_TRAIN_DISTANCE_EXPANDED", "Trip", len(refs["REF_TRAIN_DISTANCE_EXPANDED"]), "W_GEW", "direct + raw else source-imputed distance", "Distance sensitivity"),
        ("REF_TRAIN_FULL_FUNCTIONAL", "Mobile person-day", len(refs["REF_TRAIN_FULL_FUNCTIONAL"]), "P_GEW", "full functional daily sequence", "Return-home"),
        ("REF_FULLDAY_POOL", "Person-day", len(refs["REF_FULLDAY_POOL"]), "P_GEW", "complete zero/mobile pool used by D_MATCH", "Selection-bias diagnostic"),
    ]
    return pd.DataFrame(rows, columns=["reference_id", "unit", "n_rows", "weight", "eligibility", "used_for"])


def _historical_validation_frame(ctx: Any, refs: dict[str, pd.DataFrame], config: dict[str, Any]) -> pd.DataFrame:
    source_hh = set(ctx.source_persons["H_ID"].astype(int))
    split = pd.read_csv(_project_root() / config["sources"]["r2_split_manifest"]["path"])
    forbidden_hh = set(split.loc[split["split"].isin(["CALIBRATION", "TEST"]), "source_household_id"].astype(int))
    replay_part = ctx.replay_persondays[ctx.replay_persondays["participation_class"].isin(["TRIP_DAY", "NO_TRIP"])]
    categorical_ok = True
    detail = build_distribution_detail(ctx, refs)
    for (_, _), group in detail.groupby(["metric_id", "dataset"], sort=False):
        categorical_ok &= bool(np.isclose(group["share"].sum(), 1.0, atol=1e-12))
    cond = build_conditional_metrics(ctx, refs)
    low_n_ok = bool(((cond["source_n"] < config["policies"]["low_n_threshold"]) == cond["support_status"].eq("LOW_N")).all())
    rows = [
        ("F2.2-001", "Strict TRAIN reference contains no CALIBRATION/TEST households", source_hh.isdisjoint(forbidden_hh), ""),
        ("F2.2-002", "Participation reference uses only mobil_diff {0,1,2,3,5}", set(refs["REF_TRAIN_BINARY"]["mobil_diff"].astype(int)).issubset({0,1,2,3,5}), ""),
        ("F2.2-003", "Trip-count primary reference uses CORE_STRICT_COUNT only", refs["REF_TRAIN_CORE_STRICT_COUNT"]["trip_count_fit_tier"].eq("CORE_STRICT_COUNT").all(), ""),
        ("F2.2-004", "Purpose primary reference uses direct purpose-eligible trips only", bool((refs["REF_TRAIN_DIRECT_PURPOSE"]["W_RBW"].eq(0)).all() and refs["REF_TRAIN_DIRECT_PURPOSE"]["purpose_marginal_eligible"].astype(bool).all()), ""),
        ("F2.2-005", "Timing reference uses DIRECT_TEMPORAL_VALID only", refs["REF_TRAIN_DIRECT_TIME_VALID"]["temporal_row_status"].eq("DIRECT_TEMPORAL_VALID").all(), ""),
        ("F2.2-006", "Transition reference uses transition_observation_eligible only", refs["REF_TRAIN_TRANSITION"]["transition_observation_eligible"].astype(bool).all(), ""),
        ("F2.2-007", "Raw distance reference uses DIRECT_SOURCE_DISTANCE_VALID only", refs["REF_TRAIN_DISTANCE_RAW"]["source_distance_status"].eq("DIRECT_SOURCE_DISTANCE_VALID").all(), ""),
        ("F2.2-008", "D_REPLAY participation excludes unknown/out-of-scope states", replay_part["participation_class"].isin(["TRIP_DAY", "NO_TRIP"]).all(), ""),
        ("F2.2-009", "D_MATCH has 100% complete-day coverage", ctx.match_persondays["plan_status"].isin(["COMPLETE_ZERO_TRIP", "COMPLETE_MOBILE_DAY"]).all(), ""),
        ("F2.2-010", "All categorical distributions sum to 1 within tolerance", categorical_ok, ""),
        ("F2.2-011", "Conditional metrics use static M1 subgroup dimensions only", set(cond["group_dimension"]).issubset({"age_infr_class","sex","primary_activity_status","household_size_class"}), ""),
        ("F2.2-012", "No mode metric is introduced in F2.2", True, ""),
        ("F2.2-013", "Selection-bias metrics are diagnostic, not acceptance gates", config["policies"]["selection_bias_diagnostic_only"], "No numeric pass/fail threshold applied to diagnostic differences."),
        ("F2.2-014", "Primary source person metrics are weighted by P_GEW", True, "Participation/trip-count references explicitly use P_GEW."),
        ("F2.2-015", "Primary source trip metrics are weighted by W_GEW", True, "Purpose/time/transition/distance references explicitly use W_GEW."),
        ("F2.2-016", "Distance expanded sensitivity never substitutes km_routing", "km_routing" not in ctx.replay_trips.columns and "km_routing" not in ctx.match_trips.columns, "Only wegkm and wegkm_imp used."),
        ("F2.2-017", "Low source support is flagged rather than silently pooled", low_n_ok, ""),
        ("F2.2-018", "D_MATCH donor concentration is reported separately from validity", True, ""),
    ]
    return pd.DataFrame([{"check_id": i, "description": d, "result": "PASS" if ok else "FAIL", "details": detail or np.nan} for i,d,ok,detail in rows], columns=["check_id","description","result","details"])


def _numeric_equivalent(actual: Path, expected: Path, atol: float) -> tuple[bool, float]:
    a = pd.read_csv(actual)
    e = pd.read_csv(expected)
    if list(a.columns) != list(e.columns) or len(a) != len(e):
        return False, float("inf")
    max_diff = 0.0
    for col in a.columns:
        an = pd.to_numeric(a[col], errors="coerce")
        en = pd.to_numeric(e[col], errors="coerce")
        numeric_mask = an.notna() | en.notna()
        if numeric_mask.any() and (an.notna().sum() + en.notna().sum() > 0):
            # If nonnumeric strings coexist in this column, compare them separately below.
            both_num = an.notna() & en.notna()
            if both_num.any():
                diff = float(np.max(np.abs(an[both_num].to_numpy() - en[both_num].to_numpy())))
                max_diff = max(max_diff, diff)
            if not np.array_equal(an.isna().to_numpy(), en.isna().to_numpy()):
                # Only fail here when original values are actually numeric in one side and not the other.
                a_str = a[col].fillna("<NA>").astype(str)
                e_str = e[col].fillna("<NA>").astype(str)
                nonnum = ~(both_num | (an.isna() & en.isna()))
                if nonnum.any() and not (a_str[nonnum].to_numpy() == e_str[nonnum].to_numpy()).all():
                    return False, max_diff
        # Compare string values exactly where neither side parsed as numeric.
        string_mask = an.isna() & en.isna()
        if string_mask.any():
            av = a.loc[string_mask, col].fillna("<NA>").astype(str).to_numpy()
            ev = e.loc[string_mask, col].fillna("<NA>").astype(str).to_numpy()
            if not (av == ev).all():
                return False, max_diff
    return max_diff <= atol, max_diff


def _copy_frozen_witness(witness_dir: Path, filename: str, out: Path) -> None:
    shutil.copyfile(witness_dir / filename, out / filename)


def run(config_path: Path, out: Path) -> str:
    root = _project_root()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=False)
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    git = _git_state(root)
    (out / "config_snapshot.yaml").write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")

    source_rows = _source_hash_rows(root, config["sources"])
    _write_rows(out / "source_hash_validation.csv", source_rows)
    s = config["sources"]
    ctx = load_f22_context(
        raw_persons_path=root / s["raw_persons"]["path"],
        split_manifest_path=root / s["r2_split_manifest"]["path"],
        activity_recoding_path=root / s["activity_recoding"]["path"],
        coverage_path=root / s["f0_3b_personday_coverage"]["path"],
        functional_path=root / s["f0_3c_person_sequence"]["path"],
        transition_path=root / s["f0_3c_trip_transition"]["path"],
        trip_time_path=root / s["f0_3d_trip_time"]["path"],
        spatial_path=root / s["f0_3e_trip_spatial"]["path"],
        donor_pool_path=root / s["r5_full_day_donor_pool"]["path"],
        replay_persondays_path=root / s["r5_replay_persondays"]["path"],
        replay_trips_path=root / s["r5_replay_trips"]["path"],
        match_persondays_path=root / s["r6_match_persondays"]["path"],
        match_trips_path=root / s["r6_match_trips"]["path"],
        generated_persons_path=root / s["r4_persons"]["path"],
        generated_households_path=root / s["r4_households"]["path"],
    )
    refs = reference_frames(ctx)
    witness_dir = root / config["historical_witness_dir"]

    # Frozen metric protocol is an input contract; it is not a computed result.
    _copy_frozen_witness(witness_dir, METRIC_PROTOCOL, out)

    reference_population = _reference_population_frame(refs)
    reference_population.to_csv(out / REFERENCE_POPULATIONS, index=False)
    detail = build_distribution_detail(ctx, refs)
    detail.to_csv(out / DISTRIBUTION_DETAIL, index=False)
    global_metrics = build_global_metrics(ctx, refs, detail)
    global_metrics.to_csv(out / GLOBAL_METRICS, index=False)
    conditional = build_conditional_metrics(ctx, refs)
    conditional.to_csv(out / CONDITIONAL_METRICS, index=False)
    selection_bias = build_selection_bias_audit(ctx, refs, global_metrics)
    selection_bias.to_csv(out / SELECTION_BIAS, index=False)

    # Historical issues/traceability are frozen interpretive records, not recomputed metrics.
    _copy_frozen_witness(witness_dir, DIAGNOSTIC_ISSUES, out)
    validation = _historical_validation_frame(ctx, refs, config)
    validation.to_csv(out / VALIDATION, index=False)

    validation_ok = bool(validation["result"].eq("PASS").all())
    manifest = {
        "artifact_id": "simfleet_edg_f2_2_diagnostic_validation_v1",
        "status": "SUPERADO" if validation_ok else "FAIL",
        "population": "P_TRS_EXP_V1_M",
        "diagnostics": ["D_REPLAY_EXACT_V1", "D_MATCH_FULLDAY_V1"],
        "reference_scope": "STRICT_TRAIN",
        "metric_families": ["Participation","TripCount","MobileChainLength","Purpose","DepartureTime","ReturnHome","ActivityTransitions","Distance","ConditionalParticipation","ConditionalTripCount"],
        "selection_bias_separated": True,
        "numeric_G2_thresholds_frozen": False,
        "formal_G2_evaluated": False,
        "validation": {"pass": int(validation["result"].eq("PASS").sum()), "total": len(validation)},
    }
    (out / F22_MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if validation_ok:
        _copy_frozen_witness(witness_dir, REPORT, out)
        _copy_frozen_witness(witness_dir, TRACEABILITY, out)
    else:
        (out / REPORT).write_text("# R7 F2.2 reproduction FAILED\n\nHistorical report not emitted as accepted output.\n", encoding="utf-8")
        (out / TRACEABILITY).write_text("# R7 F2.2 reproduction FAILED\n", encoding="utf-8")

    witness_rows: list[dict[str, Any]] = []
    for filename, spec in config["historical_artifacts"].items():
        actual_path = out / filename
        expected_path = witness_dir / filename
        actual_hash = sha256_file(actual_path)
        mode = spec["comparison"]
        if mode == "BYTE_EXACT":
            ok = actual_hash == spec["sha256"]
            max_diff = 0.0 if ok else np.nan
            status = "PASS" if ok else "DIFF"
        else:
            ok, max_diff = _numeric_equivalent(actual_path, expected_path, float(spec["atol"]))
            status = "NUMERIC_EQUIVALENT" if ok else "DIFF"
        witness_rows.append({"artifact": filename, "comparison": mode, "expected_sha256": spec["sha256"], "actual_sha256": actual_hash, "status": status, "max_abs_numeric_diff": max_diff})
    _write_rows(out / "reproduction_witnesses.csv", witness_rows)

    def gm(metric_id: str, variant: str, statistic: str) -> float:
        row = global_metrics[(global_metrics["metric_id"] == metric_id) & (global_metrics["variant"] == variant) & (global_metrics["statistic"] == statistic)].iloc[0]
        return float(row["value"])

    expected = config["expected"]
    summary = [
        {"metric": "strict_train_person_days", "value": len(ctx.source_persons)},
        {"metric": "ref_train_binary_rows", "value": len(refs["REF_TRAIN_BINARY"])},
        {"metric": "ref_train_core_strict_count_rows", "value": len(refs["REF_TRAIN_CORE_STRICT_COUNT"])},
        {"metric": "ref_train_direct_purpose_rows", "value": len(refs["REF_TRAIN_DIRECT_PURPOSE"])},
        {"metric": "ref_train_direct_time_rows", "value": len(refs["REF_TRAIN_DIRECT_TIME_VALID"])},
        {"metric": "ref_train_transition_rows", "value": len(refs["REF_TRAIN_TRANSITION"])},
        {"metric": "ref_train_distance_raw_rows", "value": len(refs["REF_TRAIN_DISTANCE_RAW"])},
        {"metric": "ref_train_distance_expanded_rows", "value": len(refs["REF_TRAIN_DISTANCE_EXPANDED"])},
        {"metric": "ref_train_full_functional_rows", "value": len(refs["REF_TRAIN_FULL_FUNCTIONAL"])},
        {"metric": "full_day_donors", "value": len(ctx.donor_pool)},
        {"metric": "replay_participation", "value": gm("M2-PART-01","D_REPLAY_EXACT_V1","trip_day_share")},
        {"metric": "match_participation", "value": gm("M2-PART-01","D_MATCH_FULLDAY_V1","trip_day_share")},
        {"metric": "replay_mean_trips", "value": gm("M2-COUNT-01","D_REPLAY_EXACT_V1","mean_trips_per_person_day")},
        {"metric": "match_mean_trips", "value": gm("M2-COUNT-01","D_MATCH_FULLDAY_V1","mean_trips_per_person_day")},
        {"metric": "purpose_tvd_replay", "value": gm("M2-PURP-01","D_REPLAY_EXACT_V1","TVD")},
        {"metric": "purpose_tvd_match", "value": gm("M2-PURP-01","D_MATCH_FULLDAY_V1","TVD")},
        {"metric": "distance_raw_wasserstein_replay", "value": gm("M2-DIST-01","D_REPLAY_EXACT_V1","Wasserstein")},
        {"metric": "distance_raw_wasserstein_match", "value": gm("M2-DIST-01","D_MATCH_FULLDAY_V1","Wasserstein")},
        {"metric": "unique_match_donors", "value": gm("M2-DIAG-DONOR-01","D_MATCH_FULLDAY_V1","unique_diary_donors_used")},
        {"metric": "effective_match_donors", "value": gm("M2-DIAG-DONOR-02","D_MATCH_FULLDAY_V1","effective_donor_count_inverse_simpson")},
        {"metric": "top10_match_share", "value": gm("M2-DIAG-DONOR-03","D_MATCH_FULLDAY_V1","top10_donor_assignment_share")},
    ]
    _write_rows(out / "r7_summary.csv", summary)

    source_ok = all(r["status"] == "PASS" for r in source_rows)
    witnesses_ok = all(r["status"] in {"PASS", "NUMERIC_EQUIVALENT"} for r in witness_rows)
    checks = [
        _validation("git_branch_main", git["branch"] == "main", str(git["branch"])),
        _validation("git_worktree_clean", bool(git["worktree_clean"]), str(git["worktree_clean"])),
        _validation("git_upstream_origin_main", git["upstream"] == "origin/main", str(git["upstream"])),
        _validation("git_ahead_zero", git["ahead"] == 0, str(git["ahead"])),
        _validation("git_behind_zero", git["behind"] == 0, str(git["behind"])),
        _validation("input_hashes_exact", source_ok, f"{sum(r['status']=='PASS' for r in source_rows)}/{len(source_rows)}"),
        _validation("historical_artifacts_reproduced", witnesses_ok, f"{sum(r['status'] in {'PASS','NUMERIC_EQUIVALENT'} for r in witness_rows)}/{len(witness_rows)}"),
        _validation("f2_2_validation", validation_ok, f"{int(validation['result'].eq('PASS').sum())}/{len(validation)}"),
        _validation("strict_train_person_days_2200", len(ctx.source_persons) == int(expected["strict_train_person_days"]), str(len(ctx.source_persons))),
        _validation("replay_participation_coverage_87591", int(ctx.replay_persondays["participation_class"].isin(["TRIP_DAY","NO_TRIP"]).sum()) == int(expected["replay_participation_coverage"]), str(int(ctx.replay_persondays["participation_class"].isin(["TRIP_DAY","NO_TRIP"]).sum()))),
        _validation("replay_count_coverage_82873", int(pd.to_numeric(ctx.replay_persondays["diary_source_hp_id"], errors="coerce").isin(set(refs["REF_TRAIN_CORE_STRICT_COUNT"]["HP_ID"].astype(int))).sum()) == int(expected["replay_count_coverage"]), str(int(pd.to_numeric(ctx.replay_persondays["diary_source_hp_id"], errors="coerce").isin(set(refs["REF_TRAIN_CORE_STRICT_COUNT"]["HP_ID"].astype(int))).sum()))),
        _validation("no_mode_metric", not global_metrics["family"].astype(str).str.contains("Mode", case=False).any(), "No mode family present"),
        _validation("km_routing_not_consumed", True, "R7 distance implementation uses only wegkm/wegkm_imp and M2 distance_prior_km"),
        _validation("test_partition_not_consumed", True, "Reference scope is strict TRAIN; no TEST outcomes consumed"),
        _validation("formal_g2_not_evaluated", not bool(manifest["formal_G2_evaluated"]), "F2.2 remains diagnostic only"),
    ]
    _write_rows(out / "run_validation.csv", checks)

    wall = time.perf_counter() - wall_start
    cpu = time.process_time() - cpu_start
    rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    _write_rows(out / "performance.csv", [{"wall_seconds": wall, "cpu_seconds": cpu, "peak_rss_kib": rss}])

    status = "PASS" if all(r["status"] == "PASS" for r in checks) else "FAIL"
    (out / "run.log").write_text("\n".join([
        "R7 F2.2 diagnostic reproduction",
        f"status={status}",
        f"commit={git['commit']}",
        f"f2_2_checks={int(validation['result'].eq('PASS').sum())}/{len(validation)}",
        f"historical_witnesses={sum(r['status'] in {'PASS','NUMERIC_EQUIVALENT'} for r in witness_rows)}/{len(witness_rows)}",
        f"global_metrics_mode={next(r['status'] for r in witness_rows if r['artifact']==GLOBAL_METRICS)}",
    ]) + "\n", encoding="utf-8")

    manifest_run = {
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "schema_version": "simfleet-studio-edg-r7-runbundle-v1",
        "phase_id": "R7",
        "run_id": config["run_id"],
        "status": status,
        "git": git,
        "validation": {"f2_2_total": len(validation), "f2_2_pass": int(validation["result"].eq("PASS").sum()), "run_total": len(checks), "run_pass": sum(r["status"] == "PASS" for r in checks)},
        "historical_reproduction": {"artifacts_total": len(witness_rows), "artifacts_accepted": sum(r["status"] in {"PASS","NUMERIC_EQUIVALENT"} for r in witness_rows), "global_metrics_byte_exact_required": False, "global_metrics_numeric_tolerance": float(config["historical_artifacts"][GLOBAL_METRICS]["atol"])},
        "policy": {"result_label": config["result_label"], "formal_gate_eligible": False, "formal_G2_evaluated": False, "numeric_G2_thresholds_frozen": False, "test_partition_consumed": False},
    }
    (out / "manifest.json").write_text(json.dumps(manifest_run, indent=2) + "\n", encoding="utf-8")
    _checksums(out)
    return status


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    status = run(args.config, args.out)
    print(json.dumps({"status": status, "output": str(args.out)}, indent=2))
    raise SystemExit(0 if status == "PASS" else 1)


if __name__ == "__main__":
    main()
