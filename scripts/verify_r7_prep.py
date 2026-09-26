"""Static preparation verifier for the R7 F2.2 diagnostics overlay."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "reproduction" / "r7_f2_2_diagnostics.yaml"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
source_checks: dict[str, bool] = {}
for name, spec in config["sources"].items():
    path = ROOT / spec["path"]
    source_checks[f"source_{name}_hash"] = path.is_file() and sha256(path) == spec["sha256"]

witness_dir = ROOT / config["historical_witness_dir"]
witness_checks: dict[str, bool] = {}
for filename, spec in config["historical_artifacts"].items():
    path = witness_dir / filename
    witness_checks[f"historical_{filename}_hash"] = (
        path.is_file() and sha256(path) == spec["sha256"]
    )

expected = config["expected"]
policies = config["policies"]
checks = {
    "r7_config_present": CONFIG.is_file(),
    "r7_module_importable": (
        importlib.util.find_spec("simfleet_edg.repro.r7_f2_2_diagnostics") is not None
    ),
    "diagnostic_metrics_module_importable": (
        importlib.util.find_spec("simfleet_edg.common.diagnostic_metrics") is not None
    ),
    **source_checks,
    **witness_checks,
    "historical_artifacts_11": len(config["historical_artifacts"]) == 11,
    "expected_validation_18_of_18": (
        expected["validation_pass"] == 18 and expected["validation_total"] == 18
    ),
    "expected_strict_train_person_days_2200": expected["strict_train_person_days"] == 2200,
    "expected_ref_binary_2154": expected["ref_train_binary_rows"] == 2154,
    "expected_ref_count_2052": expected["ref_train_core_strict_count_rows"] == 2052,
    "expected_replay_participation_coverage_87591": (
        expected["replay_participation_coverage"] == 87591
    ),
    "expected_replay_count_coverage_82873": expected["replay_count_coverage"] == 82873,
    "strict_train_reference_only": policies["strict_train_reference_only"] is True,
    "test_outcomes_forbidden": policies["calibration_test_outcomes_forbidden"] is True,
    "person_weight_p_gew": policies["person_reference_weight"] == "P_GEW",
    "trip_weight_w_gew": policies["trip_reference_weight"] == "W_GEW",
    "no_mode_metric": policies["no_mode_metric"] is True,
    "km_routing_forbidden": policies["km_routing_forbidden"] is True,
    "low_n_flag_not_pool": (
        policies["low_n_threshold"] == 30 and policies["low_n_action"] == "FLAG_NOT_POOL"
    ),
    "selection_bias_diagnostic_only": policies["selection_bias_diagnostic_only"] is True,
    "numeric_g2_thresholds_not_frozen": policies["numeric_g2_thresholds_frozen"] is False,
    "formal_g2_not_evaluated": policies["formal_g2_evaluated"] is False,
    "global_metrics_numeric_equivalence_documented": (
        config["historical_artifacts"]["simfleet_edg_F2_2_global_metrics_v1.csv"][
            "comparison"
        ]
        == "NUMERIC_EQUIVALENT"
        and float(
            config["historical_artifacts"]["simfleet_edg_F2_2_global_metrics_v1.csv"][
                "atol"
            ]
        )
        == 1e-12
    ),
}
status = "PASS" if all(checks.values()) else "FAIL"
print(json.dumps({"status": status, "checks": checks}, indent=2))
raise SystemExit(0 if status == "PASS" else 1)
