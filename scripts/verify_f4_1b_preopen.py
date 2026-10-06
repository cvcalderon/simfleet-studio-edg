from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from importlib.util import find_spec
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PARENT = "8ccbb4d54601a7fdf65fe6cb549e688d2ba1558e"

EXPECTED_HASHES = {
    "data/raw/lor/lor_2021_a_lor_plr_2021_WGS84.geojson": "a19e3d75adb663225150abd833ffb2ca69cea156ff1356d342c92612e2cb3ff5",
    "data/raw/lor/lor_2021_b_lor_bzr_2021_WGS84.geojson": "6048918bfb1d74d546a0a145e996645ea6c0906e8a77718f04fcedb436c030d0",
    "data/raw/lor/lor_2021_c_lor_pgr_2021_WGS84.geojson": "8e6fcf3be62fe85fc72c71aa5c884c94b72d91d0674a868cf898c33025eaac52",
    "data/raw/lor/LOR2021-native_projection.zip": "275bcc93c5c2cfd6cc5980ad6df46730e1be703aaf76d21102a44763a93c8de0",
}

EXPECTED_NEW_FILES = {
    "configs/f4/f4_1b_m2_m3_adapter_lor_gate_v1.yaml",
    "docs/F4_1B_CANONICAL_M2_M3_CONTRACT_v1.json",
    "docs/F4_1B_M2_M3_ADAPTER_LOR_GATE_v1.md",
    "docs/F4_1B_OVERLAY_CHECKSUMS_v1.sha256",
    "docs/F4_1B_OVERLAY_FILELIST_v1.txt",
    "src/simfleet_edg/canonical/mobility.py",
    "src/simfleet_edg/demand/m2_m3_adapter.py",
    "src/simfleet_edg/spatial/__init__.py",
    "src/simfleet_edg/spatial/lor.py",
    "scripts/verify_f4_1b_preopen.py",
    "tests/test_f4_1b_contracts.py",
    "tests/test_f4_1b_lor.py",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def overlay_scope() -> bool:
    lines = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
    ).splitlines()

    modified = set()
    untracked = set()
    for line in lines:
        if not line.strip():
            continue
        path = line[3:]
        if line.startswith("??"):
            untracked.add(path)
        else:
            modified.add(path)

    return modified == {"pyproject.toml"} and untracked == EXPECTED_NEW_FILES


def checksum_manifest_ok() -> bool:
    path = ROOT / "docs/F4_1B_OVERLAY_CHECKSUMS_v1.sha256"
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, rel = line.split("  ", 1)
        target = ROOT / rel
        if not target.exists() or sha256(target) != expected:
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--static-only", action="store_true")
    args = parser.parse_args()

    checks: dict[str, bool] = {}
    checks["branch_main"] = git("branch", "--show-current") == "main"
    checks["head_exact_parent"] = git("rev-parse", "HEAD") == EXPECTED_PARENT
    checks["origin_exact_parent"] = git("rev-parse", "origin/main") == EXPECTED_PARENT
    checks["index_empty"] = git("diff", "--cached", "--name-only") == ""
    checks["overlay_scope_exact"] = overlay_scope()
    checks["overlay_checksums"] = checksum_manifest_ok()

    cfg = yaml.safe_load(
        (ROOT / "configs/f4/f4_1b_m2_m3_adapter_lor_gate_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    checks["f4_1a_parent_exact"] = cfg["required_parent_commit"] == EXPECTED_PARENT
    checks["g2_closed"] = cfg["upstream"]["g2"] == "PASS_CLOSED_DO_NOT_REOPEN"
    checks["mid_test_closed"] = (
        cfg["upstream"]["mid_test"] == "CONSUMED_BY_G2_DO_NOT_REOPEN"
    )
    checks["candidate_selection_none"] = (
        cfg["scientific_boundary"]["candidate_selection"] == "NONE"
    )
    checks["spatialization_forbidden"] = all(
        cfg["scientific_boundary"][key] == "FORBIDDEN_IN_F4_1B"
        for key in (
            "residential_assignment",
            "activity_location_assignment",
            "s_near_execution",
            "s_dist_execution",
            "s_attr_execution",
        )
    )

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    checks["spatial_extra_declared"] = (
        'spatial = ["shapely>=2,<3", "pyproj>=3.7,<4"]' in pyproject
    )
    checks["geopandas_not_required"] = "geopandas" not in pyproject.lower()
    checks["fiona_not_required"] = "fiona" not in pyproject.lower()

    g2_text = (
        ROOT / "configs/f3/f3_4g2g_heldout_test_a1_closure_v1.yaml"
    ).read_text(encoding="utf-8")
    checks["authoritative_g2_closure_present"] = (
        "HELDOUT_TEST_A1_CLOSED_G2_PASS" in g2_text
    )

    for rel, expected in EXPECTED_HASHES.items():
        target = ROOT / rel
        checks[f"hash:{rel}"] = target.exists() and sha256(target) == expected

    source_text = (
        ROOT / "src/simfleet_edg/demand/m2_m3_adapter.py"
    ).read_text(encoding="utf-8")
    checks["adapter_no_calibration_path"] = "CALIBRATION" not in source_text
    checks["adapter_no_test_path"] = "MiD_TEST" not in source_text and "/TEST/" not in source_text
    checks["adapter_no_dgen_execution"] = "generate_pipeline(" not in source_text

    environment: dict[str, object] = {
        "shapely": find_spec("shapely") is not None,
        "pyproj": find_spec("pyproj") is not None,
    }

    if not args.static_only:
        checks["shapely_importable"] = bool(environment["shapely"])
        checks["pyproj_importable"] = bool(environment["pyproj"])
        if checks["shapely_importable"] and checks["pyproj_importable"]:
            from simfleet_edg.spatial.lor import audit_all_lor

            lor = audit_all_lor(
                ROOT / "data/raw/lor/lor_2021_a_lor_plr_2021_WGS84.geojson",
                ROOT / "data/raw/lor/lor_2021_b_lor_bzr_2021_WGS84.geojson",
                ROOT / "data/raw/lor/lor_2021_c_lor_pgr_2021_WGS84.geojson",
            )
            checks["lor_environment_gate"] = bool(lor["passed"])
            environment["lor"] = lor
        else:
            checks["lor_environment_gate"] = False
    else:
        environment["lor"] = "SKIPPED_STATIC_ONLY"

    failed = sorted(key for key, value in checks.items() if not value)
    result = {
        "phase": "F4.1b",
        "mode": "STATIC_ONLY" if args.static_only else "FULL_ENVIRONMENT_GATE",
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "environment": environment,
        "failed": failed,
        "next_phase_if_pass": "F4.1c_LOCATION_SUPPLY_DESIGN_AND_EVIDENCE_BINDING",
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
