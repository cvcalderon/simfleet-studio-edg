from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PARENT = "0958a673f0527b5bc87c16cb041e620f085ead87"

PROTECTED_HASHES = {
    "pyproject.toml": "312fd2d395ad44ae06303307982373e58773539aeb1654b7d31a5a12bd2aa882",
    "src/simfleet_edg/canonical/mobility.py": "881fd12eb59d89ebe48a30a1e5f267f55051720dc265471ca796f154afcb9d2e",
    "src/simfleet_edg/demand/m2_m3_adapter.py": "b3f383be6aaa73cc0393e44ce32408c98b5383e8198ed08373d1e46bf366ab8e",
    "src/simfleet_edg/spatial/lor.py": "907ac33d31506bb9fa7325232e212e13ec894ffc1212f1b7feb4219dbe4edea7",
    "src/simfleet_edg/spatial/osm_source.py": "3e77f005ebe52422600bcf39a849b9f7909bb5bc24257dbd571028c74a50ef9c",
    "src/simfleet_edg/spatial/osm_registry.py": "79100057759f68062bc23d219cfa17c47a6b887e7b821c9164794556b39a80d4",
    "src/simfleet_edg/spatial/osm_audit.py": "17df95d6a8888845b639ae8ff6a6b1eb8f11044fdfca0afd07b737aa0bf20e73",
    "src/simfleet_edg/repro/f4_1c_b_osm_audit.py": "2fc3eba8fd74f2596be13e3d30467c5bc382fd17e5018ad57f6fee66122d6485",
    "configs/f4/f4_1a_m3_design_freeze_v1.yaml": "84b4c0c5f916a8b84ca546da9a3e2ac011a04dd08c21c2ce942f206c2627d1a0",
    "configs/f4/f4_1b_m2_m3_adapter_lor_gate_v1.yaml": "61f9b356118a001311ccb090369454d750dbb5844e2596eb2bce8cbe1e515478",
    "configs/f4/f4_1c_a2_external_source_contract_v1.yaml": "05f13a01307fd1076df777f8d9fdc2e875313aec2904c9b7bf8909999c3f3096",
    "configs/f4/f4_1c_a3_eligibility_policy_v1.yaml": "7713d8a7e12032c69483726bf25091d8048e30f4a58798b4fdeb7c1b36242ffb",
    "configs/f4/f4_1c_a4_attractiveness_capacity_policy_v1.yaml": "535d2a7f38c5ee982671ce02ab97ec9e1c0174c20f0d2339f07bff50766af432",
    "configs/f4/f4_1c_b_acquisition_preopen_v1.yaml": "ad204fb5cebd4869e7b8b3efd3db3a967d0be6ba2633dc8d83f1888cb031c661",
}

IMPLEMENTATION_MODULES = (
    "src/simfleet_edg/spatial/lor_lookup.py",
    "src/simfleet_edg/spatial/location_supply.py",
    "src/simfleet_edg/spatial/residential_anchor.py",
    "src/simfleet_edg/repro/f4_1c_c_materialize.py",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def expected_overlay() -> set[str]:
    path = ROOT / "docs/F4_1C_C_OVERLAY_FILELIST_v1.txt"
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def overlay_scope_exact() -> bool:
    lines = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    observed = {line[3:] for line in lines if line.strip()}
    return observed == expected_overlay() and all(line.startswith("??") for line in lines if line.strip())


def overlay_checksums_ok() -> bool:
    manifest = ROOT / "docs/F4_1C_C_OVERLAY_CHECKSUMS_v1.sha256"
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
    return covered == expected_overlay() - {"docs/F4_1C_C_OVERLAY_CHECKSUMS_v1.sha256"}


def protected_content_ok() -> bool:
    return all((ROOT / relative).is_file() and sha256(ROOT / relative) == expected for relative, expected in PROTECTED_HASHES.items())


def implementation_boundary_ok() -> bool:
    forbidden_names = {
        "SpatialTripIntent",
        "SpatializedDayPlan",
        "S_NEAR",
        "S_DIST",
        "S_ATTR",
    }
    forbidden_import_prefixes = ("urllib", "requests", "httpx", "aiohttp")
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


def design_sync_ok() -> bool:
    expected = {
        "configs/f4/f4_1c_b_main_closure_v1.yaml": "879867c04f71a1a71a1796beb2e5e499bd014cf89ce9e3cffef933a6ba2ee372",
        "configs/f4/f4_1c_c_design_freeze_v2.yaml": "8cd7564dd000241c423a43f85e8cf97356dbe434b55d6720938af01eb5b090bd",
    }
    return all(sha256(ROOT / relative) == digest for relative, digest in expected.items())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--static-only", action="store_true")
    args = parser.parse_args()

    checks: dict[str, bool] = {}
    if args.static_only:
        checks["git_gate"] = True
        checks["overlay_scope_exact"] = True
        checks["python_3_12"] = True
    else:
        checks["branch_main"] = git("branch", "--show-current") == "main"
        checks["head_exact_parent"] = git("rev-parse", "HEAD") == EXPECTED_PARENT
        checks["origin_exact_parent"] = git("rev-parse", "origin/main") == EXPECTED_PARENT
        checks["index_empty"] = git("diff", "--cached", "--name-only") == ""
        checks["overlay_scope_exact"] = overlay_scope_exact()
        checks["python_3_12"] = sys.version_info[:2] == (3, 12)

    checks["protected_content"] = protected_content_ok()
    checks["design_sync"] = design_sync_ok()
    checks["overlay_checksums"] = overlay_checksums_ok()
    checks["implementation_boundary"] = implementation_boundary_ok()
    checks["overlay_count_28"] = len(expected_overlay()) == 28
    checks["pyproject_unchanged"] = sha256(ROOT / "pyproject.toml") == PROTECTED_HASHES["pyproject.toml"]

    failed = sorted(name for name, passed in checks.items() if not passed)
    payload = {
        "phase": "F4.1c-C",
        "mode": "STATIC_ONLY" if args.static_only else "PRE_COMMIT_FULL",
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed": failed,
        "official_materialization_authorized_before_commit": False,
        "terminal_push_authorized": False,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
