from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PARENT = "877e718a8c3fe088158eafa6332bdfb466a81213"
OVERLAY = [
    "configs/f4/f4_1a_m3_design_freeze_v1.yaml",
    "docs/F4_1A_ENTRY_AUDIT_DECISION_v1.json",
    "docs/F4_1A_M3_CONTRACT_AND_SPATIAL_SUPPLY_DESIGN_FREEZE_v1.md",
    "docs/F4_1A_OPEN_BINDINGS_v1.csv",
    "docs/F4_1A_OVERLAY_CHECKSUMS_v1.sha256",
    "docs/F4_1A_OVERLAY_FILELIST_v1.txt",
    "docs/F4_1A_SPATIAL_CANDIDATE_MATRIX_v1.csv",
    "docs/F4_1A_SPATIAL_EVIDENCE_ROLE_REGISTRY_v1.csv",
    "scripts/verify_f4_1a_design_freeze.py",
    "tests/test_f4_1a_design_freeze.py",
]
EXPECTED_HASHES = {
    "data/raw/lor/lor_2021_a_lor_plr_2021_WGS84.geojson": "a19e3d75adb663225150abd833ffb2ca69cea156ff1356d342c92612e2cb3ff5",
    "data/raw/lor/lor_2021_b_lor_bzr_2021_WGS84.geojson": "6048918bfb1d74d546a0a145e996645ea6c0906e8a77718f04fcedb436c030d0",
    "data/raw/lor/lor_2021_c_lor_pgr_2021_WGS84.geojson": "8e6fcf3be62fe85fc72c71aa5c884c94b72d91d0674a868cf898c33025eaac52",
    "data/raw/lor/LOR2021-native_projection.zip": "275bcc93c5c2cfd6cc5980ad6df46730e1be703aaf76d21102a44763a93c8de0",
}

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

def main() -> int:
    checks = {}
    checks["branch_main"] = git("branch", "--show-current") == "main"
    checks["head_exact_parent"] = git("rev-parse", "HEAD") == EXPECTED_PARENT
    checks["origin_exact_parent"] = git("rev-parse", "origin/main") == EXPECTED_PARENT
    checks["index_empty"] = git("diff", "--cached", "--name-only") == ""
    status = subprocess.check_output(
        [
            "git",
            "status",
            "--porcelain",
            "--untracked-files=all",
        ],
        cwd=ROOT,
        text=True,
    ).splitlines()
    actual = sorted(line[3:] for line in status if line.strip())
    checks["overlay_scope_exact"] = actual == sorted(OVERLAY)
    for rel, expected in EXPECTED_HASHES.items():
        p = ROOT / rel
        checks[f"hash:{rel}"] = p.exists() and sha256(p) == expected
    cfg = yaml.safe_load((ROOT / "configs/f4/f4_1a_m3_design_freeze_v1.yaml").read_text(encoding="utf-8"))
    checks["g1_closed"] = cfg["upstream"]["g1"] == "PASS_CLOSED"
    checks["g2_closed"] = cfg["upstream"]["g2"] == "PASS_CLOSED_DO_NOT_REOPEN"
    checks["test_consumed"] = cfg["upstream"]["mid_test"] == "CONSUMED_BY_G2_DO_NOT_REOPEN"
    checks["population_exact"] = cfg["upstream"]["accepted_population"]["candidate_id"] == "P_CONSTR_RMIN_V2_HD_U"
    checks["mode_blind"] = cfg["m3_scope"]["mode_blind"] is True
    checks["winner_none"] = cfg["candidate_families"]["winner"] == "NONE"
    checks["topology_deferred"] = cfg["spatial_evidence"]["lor_2021"]["topology_validation"] == "DEFERRED_TO_F4_1B_ENVIRONMENT_GATE"
    with (ROOT / "docs/F4_1A_SPATIAL_CANDIDATE_MATRIX_v1.csv").open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    checks["candidate_ids_exact"] = [r["candidate_id"] for r in rows] == ["S_NEAR", "S_DIST", "S_ATTR"]
    checks["selection_none"] = all(r["selection_status"] == "NOT_YET_AUTHORIZED" for r in rows)
    with (ROOT / "docs/F4_1A_SPATIAL_EVIDENCE_ROLE_REGISTRY_v1.csv").open(encoding="utf-8", newline="") as fh:
        roles = {r["evidence_id"]: r for r in csv.DictReader(fh)}
    checks["mid_test_forbidden"] = roles["MID-TEST"]["role"] == "FORBIDDEN_CONSUMED"
    checks["future_mode_forbidden"] = roles["M5-MODE"]["role"] == "FORBIDDEN_FUTURE_INFORMATION"
    checksum_ok = True
    for line in (ROOT / "docs/F4_1A_OVERLAY_CHECKSUMS_v1.sha256").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, rel = line.split("  ", 1)
        p = ROOT / rel
        if not p.exists() or sha256(p) != expected:
            checksum_ok = False
    checks["overlay_checksums"] = checksum_ok
    failed = sorted(k for k,v in checks.items() if not v)
    print(json.dumps({"phase":"F4.1a","status":"PASS" if not failed else "FAIL","checks":checks,"failed":failed,"next_phase_if_pass":"F4.1b_M2_TO_M3_CANONICAL_ADAPTER_AND_LOR_ENVIRONMENT_GATE"}, indent=2, sort_keys=True))
    return 0 if not failed else 1

if __name__ == "__main__":
    raise SystemExit(main())
