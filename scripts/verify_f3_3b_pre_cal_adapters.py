from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path.cwd()
CONFIG = ROOT / "configs/f3/f3_3b_cal_adapters_v1.yaml"
CHECKSUMS = ROOT / "docs/F3_3B_CAL_ADAPTERS_OVERLAY_CHECKSUMS_v1.sha256"
FILELIST = ROOT / "docs/F3_3B_CAL_ADAPTERS_OVERLAY_FILELIST_v1.txt"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def main() -> None:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}
    checks["phase_exact"] = cfg["phase"] == "F3.3b"
    checks["cal_unopened"] = cfg["cal_partition"] == "UNOPENED"
    checks["test_sealed"] = cfg["test_partition"] == "SEALED"
    checks["selection_none"] = cfg["candidate_selection"] == "NONE"
    checks["cal_rows_read_zero"] = int(cfg["cal_rows_read"]) == 0
    checks["modes_exact"] = cfg["adapter_contract"]["evaluation_modes"] == ["ISOLATED", "PROPAGATED"]
    checks["teacher_forcing_runtime_false"] = cfg["adapter_contract"]["teacher_forcing_runtime"] is False
    checks["time_clarifications_pre_cal"] = cfg["time_runtime_clarifications"]["status"] == "FROZEN_PRE_CAL_IMPLEMENTATION_CLARIFICATIONS"
    checks["time_ref_attempts_100"] = cfg["time_runtime_clarifications"]["time_ref_rejection"]["max_rejection_attempts"] == 100
    tb = cfg["time_runtime_clarifications"]["time_b_sampling"]
    checks["time_b_independent_uniforms"] = tb["departure_duration_uniform_coupling"] == "INDEPENDENT_UNIFORMS_FROM_SAME_EVENT_SEED_STREAM"
    checks["time_b_round_half_up"] = tb["minute_integerization"] == "ROUND_HALF_UP"
    checks["time_b_attempts_100"] = tb["max_rejection_attempts"] == 100
    checks["cal_open_blocked"] = cfg["cal_opening_blocker"]["state"] == "BLOCKED"

    registry_path = ROOT / cfg["candidate_registry"]["path"]
    checks["registry_sha"] = sha(registry_path) == cfg["candidate_registry"]["sha256"]
    registry = pd.read_csv(registry_path, dtype=str)
    checks["registry_rows_31"] = len(registry) == 31

    artifact_checks = 0
    for row in registry.itertuples(index=False):
        run = ROOT / "artifacts" / "runs" / row.official_run_dir
        model = run / row.model_relpath
        manifest = run / row.artifact_manifest_relpath
        ok = model.is_file() and manifest.is_file()
        if ok:
            ok = sha(model) == row.model_sha256 and sha(manifest) == row.manifest_sha256
        checks[f"artifact:{row.artifact_id}"] = bool(ok)
        artifact_checks += 1

    lines = [line.strip() for line in CHECKSUMS.read_text(encoding="utf-8").splitlines() if line.strip()]
    checksum_ok = True
    for line in lines:
        expected, rel = line.split(None, 1)
        checksum_ok &= sha(ROOT / rel.strip()) == expected
    checks["overlay_checksums_exact"] = bool(checksum_ok)

    expected_scope = {line.strip() for line in FILELIST.read_text(encoding="utf-8").splitlines() if line.strip()}
    status_lines = git("status", "--porcelain").splitlines()
    changed = {line[3:] for line in status_lines if line}
    checks["overlay_scope_exact"] = changed == expected_scope
    checks["no_staged_changes"] = not bool(git("diff", "--cached", "--name-only"))
    checks["branch_main"] = git("branch", "--show-current") == "main"
    checks["head_exact_parent"] = git("rev-parse", "HEAD") == cfg["required_parent_commit"]
    left, right = git("rev-list", "--left-right", "--count", "HEAD...origin/main").split()
    checks["ahead_zero"] = left == "0"
    checks["behind_zero"] = right == "0"

    # Static CAL/TEST-I/O blocker: adapter implementation may load only frozen model artifacts.
    source_files = [
        ROOT / "src/simfleet_edg/evaluation/cal_adapter_common.py",
        ROOT / "src/simfleet_edg/evaluation/cal_state.py",
        ROOT / "src/simfleet_edg/evaluation/participation_adapter.py",
        ROOT / "src/simfleet_edg/evaluation/trip_count_adapter.py",
        ROOT / "src/simfleet_edg/evaluation/activity_chain_adapter.py",
        ROOT / "src/simfleet_edg/evaluation/time_schedule_adapter.py",
        ROOT / "src/simfleet_edg/evaluation/distance_prior_adapter.py",
        ROOT / "src/simfleet_edg/evaluation/cal_adapter_factory.py",
        ROOT / "src/simfleet_edg/repro/f3_3b_pre_cal_adapters.py",
    ]
    joined = "\n".join(path.read_text(encoding="utf-8") for path in source_files).lower()
    checks["no_calibration_path_literal"] = "calibration/" not in joined and "/calibration" not in joined
    checks["no_test_path_literal"] = "test/" not in joined and "/test" not in joined

    failed = [name for name, ok in checks.items() if not bool(ok)]
    print(json.dumps({
        "artifact_checks": artifact_checks,
        "cal_rows_read": 0,
        "test_rows_read": 0,
        "checks": {name: bool(ok) for name, ok in checks.items()},
        "failed": failed,
        "status": "PASS" if not failed else "FAIL",
    }, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
