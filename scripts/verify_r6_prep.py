"""Static preparation verifier for the R6 D_MATCH overlay."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "reproduction" / "r6_d_match.yaml"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
source_checks = {}
for name, spec in config["sources"].items():
    path = ROOT / spec["path"]
    source_checks[f"source_{name}_hash"] = path.is_file() and sha256(path) == spec["sha256"]

expected_tiers = config["match"]["expected_tier_counts"]
checks = {
    "r6_config_present": CONFIG.is_file(),
    "r6_module_importable": importlib.util.find_spec("simfleet_edg.repro.r6_d_match") is not None,
    "demand_match_module_importable": importlib.util.find_spec("simfleet_edg.common.demand_match") is not None,
    **source_checks,
    "expected_person_days_100000": config["match"]["generated_person_days"] == 100000,
    "expected_trip_intents_291508": config["match"]["expected_trip_intents"] == 291508,
    "expected_zero_days_15574": config["match"]["expected_zero_trip_person_days"] == 15574,
    "expected_mobile_days_84426": config["match"]["expected_mobile_person_days"] == 84426,
    "expected_t1_94322": expected_tiers["T1_EXACT_AGE_SEX_ACTIVITY_HHSIZE"] == 94322,
    "expected_t2_3929": expected_tiers["T2_RELAX_HHSIZE"] == 3929,
    "expected_t3_1535": expected_tiers["T3_RELAX_ACTIVITY_TO_EMPLOYMENT"] == 1535,
    "expected_t4_214": expected_tiers["T4_AGE_SEX"] == 214,
    "expected_t5_zero": expected_tiers["T5_AGE_ONLY"] == 0,
    "expected_t6_zero": expected_tiers["T6_GLOBAL_FALLBACK"] == 0,
    "historical_bridge_hash": config["historical_witness"]["bridge_sha256"] == "2711e5542302f4c1b3b28ee8dab8b19bc044f0c61a143645e165aa32f5d437b5",
    "self_match_forbidden": config["policies"]["self_diary_match_forbidden"] is True,
    "test_partition_sealed": config["policies"]["test_partition_sealed"] is True,
    "km_routing_forbidden": config["policies"]["distance_routing_not_used"] is True,
    "individual_hash_gap_documented": config["scope_note"]["issue_id"] == "R6-WITNESS-001",
}
status = "PASS" if all(checks.values()) else "FAIL"
print(json.dumps({"status": status, "checks": checks}, indent=2))
raise SystemExit(0 if status == "PASS" else 1)
