from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/design/f3_1a_dgen_contract_v1.yaml"
REGISTRY = ROOT / "docs/F3_1a_INFORMATION_FEATURE_REGISTRY_v1.csv"
MAPPING = ROOT / "docs/F3_1a_COMPONENT_TARGET_MAPPING_v1.csv"
INVARIANTS = ROOT / "docs/F3_1a_BOUNDARY_INVARIANTS_v1.csv"
DECISIONS = ROOT / "docs/F3_1a_DECISION_REGISTER_v1.csv"

EXPECTED_COMPONENTS = [
    "DG_PARTICIPATION",
    "DG_TRIP_COUNT",
    "DG_ACTIVITY_CHAIN",
    "DG_TIME_SCHEDULE",
    "DG_DISTANCE_PRIOR",
]
VALID_CLASSES = {
    "ALLOWED_RUNTIME",
    "FIT_ONLY_EVIDENCE",
    "FORBIDDEN_FUTURE_INFORMATION",
    "IDENTIFIER_PROVENANCE_ONLY",
}
FORBIDDEN_OUTPUTS = {
    "exact_destination_coordinate",
    "generated_destination_coordinate",
    "route_geometry",
    "feasible_alternatives",
    "observed_mode",
    "chosen_mode",
    "execution_outcome",
    "km_routing",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def verify() -> dict[str, object]:
    cfg = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    reg = read_csv(REGISTRY)
    mapping = read_csv(MAPPING)
    inv = read_csv(INVARIANTS)
    dec = read_csv(DECISIONS)

    allowed_runtime = {r["field_or_group"] for r in reg if r["information_class"] == "ALLOWED_RUNTIME"}
    identifier_runtime = [
        r["field_or_group"]
        for r in reg
        if r["information_class"] == "IDENTIFIER_PROVENANCE_ONLY"
        and "predictor" in r["runtime_role"].lower()
    ]
    weight_runtime = [
        r["field_or_group"]
        for r in reg
        if r["field_or_group"] in {"P_GEW", "W_GEW"}
        and r["information_class"] == "ALLOWED_RUNTIME"
    ]
    forbidden_leaks = sorted(
        f for f in FORBIDDEN_OUTPUTS if f in allowed_runtime
    )
    output_forbidden = set(cfg["output_contract"]["TripIntent"]["forbidden_fields"])

    checks = {
        "contract_present": CONTRACT.exists(),
        "component_order_exact": cfg["component_order"] == EXPECTED_COMPONENTS,
        "five_components_declared": set(cfg["components"]) == set(EXPECTED_COMPONENTS),
        "registry_nonempty": len(reg) >= 40,
        "registry_classes_valid": all(r["information_class"] in VALID_CLASSES for r in reg),
        "no_forbidden_runtime_leak": not forbidden_leaks,
        "identifiers_not_predictors": not identifier_runtime,
        "weights_not_runtime_features": not weight_runtime,
        "forbidden_output_boundary_complete": FORBIDDEN_OUTPUTS <= output_forbidden,
        "test_partition_sealed": cfg["test_partition"] == "SEALED",
        "formal_g2_not_evaluated": cfg["formal_g2"] == "NOT_EVALUATED",
        "model_family_deferred": cfg["model_family_selection"] == "UNSELECTED_F3_1B",
        "mapping_covers_components": set(EXPECTED_COMPONENTS) <= {r["component"] for r in mapping},
        "invariants_at_least_20": len(inv) >= 20,
        "all_invariants_have_severity": all(r["severity"] in {"HARD", "REPORT"} for r in inv),
        "decision_defer_present": any(r["decision_id"] == "F3A-MODEL-001" and r["state"] == "DEFERRED_TO_F3_1B" for r in dec),
        "low_support_flag_not_pool": cfg["low_support_policy"] == "FLAG_NOT_POOL",
        "hybrid_reference_preserved": cfg["reference_identity"] == "BERLIN_HYBRID_REFERENCE_V1",
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    return {"status": status, "checks": checks, "counts": {"registry": len(reg), "mapping": len(mapping), "invariants": len(inv), "decisions": len(dec)}}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
