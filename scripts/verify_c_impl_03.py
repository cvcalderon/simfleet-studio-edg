from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "reproduction" / "r1_source_audit.yaml"
config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
checks = {
    "r1_config_present": CONFIG.is_file(),
    "r1_module_importable": importlib.util.find_spec("simfleet_edg.repro.r1_source_audit") is not None,
    "source_audit_module_importable": importlib.util.find_spec("simfleet_edg.common.source_audit") is not None,
    "source_count_17": len(config.get("sources", [])) == 17,
    "required_count_16": sum(bool(x.get("required")) for x in config.get("sources", [])) == 16,
    "raw_dirs_present": all((ROOT / "data" / "raw" / name).is_dir() for name in ("mid", "zensus", "lor")),
}
print(json.dumps({"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}, indent=2))
raise SystemExit(0 if all(checks.values()) else 1)
