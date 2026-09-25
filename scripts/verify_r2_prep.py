"""Static preparation verifier for R2 overlay."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "reproduction" / "r2_eligibility_split.yaml"

config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
checks = {
    "r2_config_present": CONFIG.is_file(),
    "r2_module_importable": importlib.util.find_spec("simfleet_edg.repro.r2_eligibility_split") is not None,
    "population_split_module_importable": importlib.util.find_spec("simfleet_edg.common.population_split") is not None,
    "expected_households_1770": config["eligibility"]["expected"]["berlin_households"] == 1770,
    "expected_private_1763": config["eligibility"]["expected"]["private_households"] == 1763,
    "expected_strict_1742": config["eligibility"]["expected"]["strict_rmin_households"] == 1742,
    "expected_strict_split": config["split"]["expected_strict_counts"] == {"TRAIN": 1219, "CALIBRATION": 263, "TEST": 260},
    "frozen_split_hash": config["split"]["expected_manifest_sha256"] == "5d0d4f2a41bc93b131de96d85192d8ff7002878e28e87515a0f88cedf1cebde8",
}
status = "PASS" if all(checks.values()) else "FAIL"
print(json.dumps({"status": status, "checks": checks}, indent=2))
raise SystemExit(0 if status == "PASS" else 1)
