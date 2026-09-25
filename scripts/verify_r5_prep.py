"""Static preparation verifier for the R5 D_REPLAY overlay."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "reproduction" / "r5_d_replay.yaml"


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

checks = {
    "r5_config_present": CONFIG.is_file(),
    "r5_module_importable": importlib.util.find_spec("simfleet_edg.repro.r5_d_replay") is not None,
    "demand_replay_module_importable": importlib.util.find_spec("simfleet_edg.common.demand_replay") is not None,
    **source_checks,
    "expected_person_days_100000": config["replay"]["generated_person_days"] == 100000,
    "expected_source_pool_2200": config["replay"]["source_diary_pool"]["expected_person_days_total"] == 2200,
    "expected_full_day_pool_1658": config["replay"]["source_diary_pool"]["expected_full_day_donors"] == 1658,
    "expected_complete_65963": config["replay"]["expected_complete_person_days"] == 65963,
    "expected_trip_intents_194457": config["replay"]["expected_trip_intents"] == 194457,
    "historical_persondays_hash": config["historical_witness"]["exact_artifacts"]["simfleet_edg_F2_1_D_REPLAY_EXACT_V1_persondays.csv"] == "bfaf6fef961d1402392948efafad387bc6527c7938a31725e331672cfd895a5e",
    "historical_trips_hash": config["historical_witness"]["exact_artifacts"]["simfleet_edg_F2_1_D_REPLAY_EXACT_V1_trips.csv"] == "5c4fedaa6db1d86aed9e51eea78ea87a991b57dd601e602cf16c5b9d33663698",
    "diagnostic_exception_explicit": config["policies"]["diagnostic_exception_to_nofuture"] is True,
    "test_partition_sealed": config["policies"]["test_partition_sealed"] is True,
    "r6_scope_note_present": config["scope_note"]["issue_id"] == "R5-SCOPE-001",
}
status = "PASS" if all(checks.values()) else "FAIL"
print(json.dumps({"status": status, "checks": checks}, indent=2))
raise SystemExit(0 if status == "PASS" else 1)
