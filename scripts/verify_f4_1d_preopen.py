from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PARENT = "eebccc7a43eb7c1ef2661da3f357c0e5b01e72ef"

PROTECTED_HASHES = {
    "src/simfleet_edg/canonical/mobility.py": "881fd12eb59d89ebe48a30a1e5f267f55051720dc265471ca796f154afcb9d2e",
    "src/simfleet_edg/demand/m2_m3_adapter.py": "b3f383be6aaa73cc0393e44ce32408c98b5383e8198ed08373d1e46bf366ab8e",
    "src/simfleet_edg/repro/f3_4g2a_joint_synthetic.py": "53838c3394edc7a8edfe740e03bba26ab1b352a682ac2f7663b45f8a59c6e9da",
    "src/simfleet_edg/spatial/location_supply.py": "60df8454a7fab475935a7e98e4c5fd5b71750ba76fa58c44b7b05af41e27027e",
    "src/simfleet_edg/spatial/residential_anchor.py": "b589fbc8b8b97a38f745f1e8bd8e1dbb56ff76ed16a62acc7f52cb9780d44857",
    "configs/f4/f4_1c_c_design_freeze_v2.yaml": "8cd7564dd000241c423a43f85e8cf97356dbe434b55d6720938af01eb5b090bd",
    "docs/F4_1B_M2_M3_ADAPTER_LOR_GATE_v1.md": "79cfaca0ddb97fac59c4d954e8c6ed2a4a4d180f9c3d6307c96028ed761be5a4",
    "docs/F3_3_CANDIDATE_ARTIFACT_REGISTRY_v1.csv": "52328037d9a57866b188166373f798da4fb97460fc794748f8f0ef3968e86ad8",
    "configs/f3/f3_4g1_joint_pipeline_registry_v1.json": "0938166da2eb9e602e09eb5b19ac8215cc3b2610a8f073e9083c6ae6af9d2faf",
}

DESIGN_HASHES = {
    "docs/F4_1D_RUNTIME_DGEN_BINDING_DESIGN_FREEZE_v1.md": "92854475c15ae74d5a1921262a5f8e80885f44a6c31c3995abc750f11f5a5ef0",
    "docs/F4_1D_RUNTIME_CONTEXT_SCHEMA_v1.csv": "255c36a949d19c7c47914aa6e6ee40970c469cee0b2d9bc71dc5acba12b2025b",
    "docs/F4_1D_MODEL_BINDINGS_v1.csv": "e7c7de60adea82fa6bbad3919774750f131fef119c3ced4a880fc5b3faff9b73",
    "docs/F4_1D_VALIDATION_PLAN_v1.csv": "db7c45397152aac4543682378e0242aa6d66fe47d6bbcb00cde8289586d96928",
}

IMPLEMENTATION_MODULES = (
    "src/simfleet_edg/demand/runtime_context.py",
    "src/simfleet_edg/demand/runtime_generator.py",
    "src/simfleet_edg/repro/f4_1d_runtime_dgen_binding.py",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def checksum_manifest_exact(relative: str, expected_count: int) -> bool:
    manifest = ROOT / relative
    if not manifest.is_file():
        return False
    entries = [line for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(entries) != expected_count:
        return False
    for line in entries:
        expected, target_relative = line.split("  ", 1)
        target = ROOT / target_relative
        if not target.is_file() or sha256(target) != expected:
            return False
    return True


def expected_overlay() -> set[str]:
    path = ROOT / "docs/F4_1D_OVERLAY_FILELIST_v1.txt"
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def overlay_scope_exact() -> bool:
    lines = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, text=True
    ).splitlines()
    observed = {line[3:] for line in lines if line.strip()}
    return observed == expected_overlay() and all(line.startswith("??") for line in lines if line.strip())


def overlay_checksums_ok() -> bool:
    manifest = ROOT / "docs/F4_1D_OVERLAY_CHECKSUMS_v1.sha256"
    if not manifest.is_file():
        return False
    covered: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        covered.add(relative)
        target = ROOT / relative
        if not target.is_file() or sha256(target) != expected:
            return False
    return covered == expected_overlay() - {"docs/F4_1D_OVERLAY_CHECKSUMS_v1.sha256"}


def protected_content_ok() -> bool:
    return all((ROOT / path).is_file() and sha256(ROOT / path) == digest for path, digest in PROTECTED_HASHES.items())


def design_content_ok() -> bool:
    return all((ROOT / path).is_file() and sha256(ROOT / path) == digest for path, digest in DESIGN_HASHES.items())


def implementation_boundary_ok() -> bool:
    forbidden_imports = (
        "simfleet_edg.spatial",
        "simfleet_edg.repro.f3_4g2a_joint_synthetic",
    )
    forbidden_names = {
        "CAL_SCENARIO_ID",
        "make_synthetic_cohort",
        "S_NEAR",
        "S_DIST",
        "S_ATTR",
        "SpatialTripIntent",
        "SpatializedDayPlan",
    }
    for relative in IMPLEMENTATION_MODULES:
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"), filename=relative)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith(forbidden_imports):
                    return False
            if isinstance(node, ast.Import):
                if any(alias.name.startswith(forbidden_imports) for alias in node.names):
                    return False
            if isinstance(node, ast.Name) and node.id in forbidden_names:
                return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--static-only", action="store_true")
    args = parser.parse_args()

    checks: dict[str, bool] = {}
    if args.static_only:
        checks["git_gate_deferred"] = True
        checks["overlay_scope_deferred"] = True
        checks["python_3_12_deferred"] = True
    else:
        checks["branch_main"] = git("branch", "--show-current") == "main"
        checks["head_exact_parent"] = git("rev-parse", "HEAD") == EXPECTED_PARENT
        checks["origin_exact_parent"] = git("rev-parse", "origin/main") == EXPECTED_PARENT
        checks["index_empty"] = git("diff", "--cached", "--name-only") == ""
        checks["overlay_scope_exact"] = overlay_scope_exact()
        checks["python_3_12"] = sys.version_info[:2] == (3, 12)

    checks["f4_1c_c_overlay_27_exact"] = checksum_manifest_exact(
        "docs/F4_1C_C_OVERLAY_CHECKSUMS_v1.sha256", 27
    )
    checks["protected_content"] = protected_content_ok()
    checks["design_content"] = design_content_ok()
    checks["overlay_checksums"] = overlay_checksums_ok()
    checks["implementation_boundary"] = implementation_boundary_ok()
    checks["overlay_count_17"] = len(expected_overlay()) == 17

    failed = sorted(name for name, passed in checks.items() if not passed)
    payload = {
        "phase": "F4.1d",
        "mode": "STATIC_ONLY" if args.static_only else "PRE_COMMIT_FULL",
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed": failed,
        "smoke_execution_authorized_before_commit": False,
        "terminal_push_authorized": False,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
