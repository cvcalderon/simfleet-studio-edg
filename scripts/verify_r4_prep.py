"""Static preparation verifier for the R4 P_TRS M-scale overlay."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "reproduction" / "r4_ptrs_m.yaml"
REFERENCE = ROOT / "configs" / "reproduction" / "reference"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
plr_ref = REFERENCE / "f1_2a_plr_universe_residual_audit_v1.csv"
activity_ref = REFERENCE / "f0_2d_activity_recoding_v1.csv"
r2_split = ROOT / config["sources"]["r2_split_manifest"]["path"]

checks = {
    "r4_config_present": CONFIG.is_file(),
    "r4_module_importable": importlib.util.find_spec("simfleet_edg.repro.r4_ptrs_m")
    is not None,
    "population_materializer_importable": importlib.util.find_spec(
        "simfleet_edg.common.population_materializer"
    )
    is not None,
    "plr_reference_hash": plr_ref.is_file()
    and sha256(plr_ref) == config["sources"]["plr_target_audit"]["sha256"],
    "activity_reference_hash": activity_ref.is_file()
    and sha256(activity_ref) == config["sources"]["activity_recoding"]["sha256"],
    "r2_split_present": r2_split.is_file(),
    "r2_split_hash": r2_split.is_file()
    and sha256(r2_split) == config["sources"]["r2_split_manifest"]["sha256"],
    "target_persons_100000": config["population"]["target_persons"] == 100000,
    "expected_households_56365": config["population"]["expected_households"]
    == 56365,
    "expected_resources_639661": config["population"]["expected_resource_relations"]
    == 639661,
    "expected_linked_89459": config["population"]["expected_linked_persons"]
    == 89459,
    "expected_roster_only_10541": config["population"]["expected_roster_only_persons"]
    == 10541,
    "generation_seed_20260922": config["population"]["generation"]["seed"]
    == 20260922,
    "zone_seed_20260923": config["population"]["geography"]["seed"] == 20260923,
    "frozen_snapshot_hash": config["historical_witness"]["snapshot_sha256"]
    == "a3a9be46286d150e1032d1872ca0e47775407ee14835980f0d5a71be92c57f7d",
    "known_geo_baseline_note_present": config["known_baseline_issue"]["issue_id"]
    == "R4-BASELINE-GEO-001",
}
status = "PASS" if all(checks.values()) else "FAIL"
print(json.dumps({"status": status, "checks": checks}, indent=2))
raise SystemExit(0 if status == "PASS" else 1)
