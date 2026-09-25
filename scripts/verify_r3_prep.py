"""Static preparation verifier for the R3 P_TRS S-scale overlay."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "reproduction" / "r3_ptrs_s.yaml"
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
    "r3_config_present": CONFIG.is_file(),
    "r3_module_importable": importlib.util.find_spec("simfleet_edg.repro.r3_ptrs_s")
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
    "target_persons_10000": config["population"]["target_persons"] == 10000,
    "expected_households_5663": config["population"]["expected_households"] == 5663,
    "expected_resources_64263": config["population"]["expected_resource_relations"]
    == 64263,
    "generation_seed_20260922": config["population"]["generation"]["seed"]
    == 20260922,
    "zone_seed_20260923": config["population"]["geography"]["seed"] == 20260923,
    "frozen_snapshot_hash": config["historical_witness"]["snapshot_sha256"]
    == "f37ffeda502929bdda4c16f0c30d297fd6c2743b4c1e50e987471c6e714f9d01",
    "known_geo_baseline_note_present": config["known_baseline_issue"]["issue_id"]
    == "R3-BASELINE-GEO-001",
}
status = "PASS" if all(checks.values()) else "FAIL"
print(json.dumps({"status": status, "checks": checks}, indent=2))
raise SystemExit(0 if status == "PASS" else 1)
