from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PARENT = "7e28e80c32dc16c478ea6916b636bafa58e917f5"

PROTECTED_HASHES = {
    "pyproject.toml": "191f6423302ec20490fe6aa98de5ab8e8b8cd17d76e060b4bdb6dc473134dd9b",
    "src/simfleet_edg/canonical/mobility.py": "881fd12eb59d89ebe48a30a1e5f267f55051720dc265471ca796f154afcb9d2e",
    "src/simfleet_edg/demand/m2_m3_adapter.py": "b3f383be6aaa73cc0393e44ce32408c98b5383e8198ed08373d1e46bf366ab8e",
    "src/simfleet_edg/spatial/lor.py": "907ac33d31506bb9fa7325232e212e13ec894ffc1212f1b7feb4219dbe4edea7",
    "configs/f4/f4_1a_m3_design_freeze_v1.yaml": "84b4c0c5f916a8b84ca546da9a3e2ac011a04dd08c21c2ce942f206c2627d1a0",
    "configs/f4/f4_1b_m2_m3_adapter_lor_gate_v1.yaml": "61f9b356118a001311ccb090369454d750dbb5844e2596eb2bce8cbe1e515478",
}

FROZEN_SYNC_HASHES = {
    "docs/F4_1C_A1_PURPOSE_TAXONOMY_AND_RESOLUTION_FREEZE_v1.md": "21e6d366c02676173b2aaa82cde2e1b80557846fe38d738306dc81564815b255",
    "docs/F4_1C_A1_ACTIVITY_RESOLUTION_REGISTRY_v1.csv": "2320e4238e02e69467595317320b8d5d411c45237a8fb7702ba12b5229d6fc0b",
    "docs/F4_1C_A2_EXTERNAL_SPATIAL_SOURCE_AND_ACQUISITION_CONTRACT_v1.md": "4dd8a6220beafb1b4600858a192027b2d9fa8968d388689ee309b3b06de2eb61",
    "configs/f4/f4_1c_a2_external_source_contract_v1.yaml": "05f13a01307fd1076df777f8d9fdc2e875313aec2904c9b7bf8909999c3f3096",
    "docs/F4_1C_A3_OSM_TAG_TO_PURPOSE_ELIGIBILITY_FREEZE_v1.md": "4d422fa956c0c7641d5490c7f2a415759e7574d86d7b1bdd14ecca0e74bce668",
    "docs/F4_1C_A3_OSM_TAG_TO_PURPOSE_ELIGIBILITY_REGISTRY_v1.csv": "3a1c7ed8ad4dfaff2de54332ec6a029682790426f2ec7a843f143c57da2056a0",
    "configs/f4/f4_1c_a3_eligibility_policy_v1.yaml": "7713d8a7e12032c69483726bf25091d8048e30f4a58798b4fdeb7c1b36242ffb",
    "docs/F4_1C_A4_ATTRACTIVENESS_CAPACITY_EVIDENCE_POLICY_FREEZE_v1.md": "aec66ad2a58843bb443430987131ce4e41348b150224063335918b3fe5655a4c",
    "docs/F4_1C_A4_ATTRACTIVENESS_CAPACITY_EVIDENCE_REGISTRY_v1.csv": "939bf6d83ee3c3b45262c8423b8ddd53778ebeef472a466f33276148901616c0",
    "configs/f4/f4_1c_a4_attractiveness_capacity_policy_v1.yaml": "535d2a7f38c5ee982671ce02ab97ec9e1c0174c20f0d2339f07bff50766af432",
    "docs/F4_1C_A5_JOINT_FREEZE_REVIEW_AND_ACQUISITION_AUTHORIZATION_v1.md": "cc8682d12a066302f15dd0c848e72a9c01879d7753f79bf7aadbc7e62ff435bd",
    "docs/F4_1C_A5_JOINT_FREEZE_REVIEW_CHECKLIST_v1.csv": "d051eddabf29c7f906fd7aeeb2096895a18125c770f6af601934dcfab4e2e4ad",
    "docs/F4_1C_A5_NORMATIVE_RECONCILIATION_AND_OPEN_BINDINGS_v1.csv": "caba1d9bab90821ee4b63e45fa62baac845123b58f3b031d5c561ac355291cf3",
}

IMPLEMENTATION_MODULES = (
    "src/simfleet_edg/spatial/osm_source.py",
    "src/simfleet_edg/spatial/osm_registry.py",
    "src/simfleet_edg/spatial/osm_audit.py",
    "src/simfleet_edg/repro/f4_1c_b_osm_audit.py",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected mapping: {path}")
    return cast(dict[str, Any], payload)


def expected_overlay() -> set[str]:
    path = ROOT / "docs/F4_1C_B_OVERLAY_FILELIST_v1.txt"
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def overlay_scope_exact() -> bool:
    lines = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    observed: set[str] = set()
    modified: set[str] = set()
    untracked: set[str] = set()
    for line in lines:
        if not line.strip():
            continue
        path = line[3:]
        observed.add(path)
        if line.startswith("??"):
            untracked.add(path)
        else:
            modified.add(path)
    expected = expected_overlay()
    return observed == expected and modified == {"pyproject.toml"} and untracked == expected - {
        "pyproject.toml"
    }


def overlay_checksums_ok() -> bool:
    manifest = ROOT / "docs/F4_1C_B_OVERLAY_CHECKSUMS_v1.sha256"
    if not manifest.is_file():
        return False
    covered: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        target = ROOT / relative
        covered.add(relative)
        if not target.is_file() or sha256(target) != expected:
            return False
    return covered == expected_overlay() - {"docs/F4_1C_B_OVERLAY_CHECKSUMS_v1.sha256"}


def historical_f4_1b_integrity() -> bool:
    manifest = ROOT / "docs/F4_1B_OVERLAY_CHECKSUMS_v1.sha256"
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        target = ROOT / relative
        if not target.is_file() or sha256(target) != expected:
            return False
    return True


def pyproject_change_exact() -> bool:
    path = ROOT / "pyproject.toml"
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    extras = cast(dict[str, list[str]], payload["project"]["optional-dependencies"])
    if extras.get("spatial") != ["shapely>=2,<3", "pyproj>=3.7,<4"]:
        return False
    if extras.get("osm") != ["osmium>=4.3,<5"]:
        return False
    if "requests" in path.read_text(encoding="utf-8").lower():
        return False
    baseline_text = path.read_text(encoding="utf-8").replace('osm = ["osmium>=4.3,<5"]\n', "")
    digest = hashlib.sha256(baseline_text.encode("utf-8")).hexdigest()
    return digest == PROTECTED_HASHES["pyproject.toml"]


def implementation_boundary_ok() -> bool:
    forbidden_import_prefixes = (
        "simfleet_edg.canonical.mobility",
        "simfleet_edg.evaluation",
    )
    forbidden_names = {
        "SpatializedDayPlan",
        "SpatialTripIntent",
        "LocationSupplyRecord",
        "ResidentialAnchor",
    }
    for relative in IMPLEMENTATION_MODULES:
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"), filename=relative)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith(forbidden_import_prefixes):
                    return False
            if isinstance(node, ast.Import):
                if any(alias.name.startswith(forbidden_import_prefixes) for alias in node.names):
                    return False
            if isinstance(node, ast.Name) and node.id in forbidden_names:
                return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--static-only", action="store_true")
    args = parser.parse_args()

    checks: dict[str, bool] = {}
    if not args.static_only:
        checks["branch_main"] = git("branch", "--show-current") == "main"
        checks["head_exact_parent"] = git("rev-parse", "HEAD") == EXPECTED_PARENT
        checks["origin_exact_parent"] = git("rev-parse", "origin/main") == EXPECTED_PARENT
        checks["index_empty"] = git("diff", "--cached", "--name-only") == ""
        checks["overlay_scope_exact"] = overlay_scope_exact()
    else:
        checks["git_gate"] = True
        checks["overlay_scope_exact"] = True

    checks["overlay_checksums"] = overlay_checksums_ok()
    checks["historical_f4_1b_integrity"] = historical_f4_1b_integrity()
    checks["pyproject_change_exact"] = pyproject_change_exact()

    for relative, expected in PROTECTED_HASHES.items():
        if relative == "pyproject.toml":
            continue
        checks[f"protected:{relative}"] = sha256(ROOT / relative) == expected
    for relative, expected in FROZEN_SYNC_HASHES.items():
        checks[f"frozen_sync:{relative}"] = sha256(ROOT / relative) == expected

    cfg = _load_yaml(ROOT / "configs/f4/f4_1c_b_acquisition_preopen_v1.yaml")
    source = cast(dict[str, Any], cfg["source"])
    checks["source_snapshot_exact"] = (
        source["source_snapshot_id"] == "OSM_GEOFABRIK_BERLIN_2026-10-04_V1"
    )
    checks["dated_pbf_exact"] = (
        source["pbf_url"]
        == "https://download.geofabrik.de/europe/germany/berlin-261004.osm.pbf"
    )
    checks["dated_md5_exact"] = (
        source["md5_url"]
        == "https://download.geofabrik.de/europe/germany/berlin-261004.osm.pbf.md5"
    )
    checks["implementation_boundary"] = implementation_boundary_ok()

    if not args.static_only:
        checks["python_3_12"] = sys.version_info[:2] == (3, 12)
        checks["osmium_importable"] = importlib.util.find_spec("osmium") is not None
        checks["shapely_importable"] = importlib.util.find_spec("shapely") is not None
        checks["pyproj_importable"] = importlib.util.find_spec("pyproj") is not None
        lor = cast(dict[str, Any], cfg["frozen_lor"])
        for level in ("plr", "bzr", "pgr"):
            spec = cast(dict[str, str], lor[level])
            target = ROOT / spec["path"]
            checks[f"lor:{level}"] = target.is_file() and sha256(target) == spec["sha256"]
    else:
        checks["environment_and_lor"] = True

    failed = sorted(name for name, passed in checks.items() if not passed)
    payload = {
        "phase": "F4.1c-B",
        "mode": "STATIC_ONLY" if args.static_only else "PRE_COMMIT_FULL",
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed": failed,
        "official_osm_acquisition_authorized_before_commit": False,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
