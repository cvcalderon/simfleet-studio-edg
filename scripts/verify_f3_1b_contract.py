from __future__ import annotations

import csv
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/design/f3_1b_model_family_contract_v1.yaml"
MATRIX = ROOT / "docs/F3_1b_CANDIDATE_MATRIX_v1.csv"
DECISIONS = ROOT / "docs/F3_1b_DECISION_REGISTER_v1.csv"


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def verify() -> dict[str, object]:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    matrix = load_rows(MATRIX)
    decisions = load_rows(DECISIONS)
    components = cfg["components"]
    expected = {
        "DG_PARTICIPATION",
        "DG_TRIP_COUNT",
        "DG_ACTIVITY_CHAIN",
        "DG_TIME_SCHEDULE",
        "DG_DISTANCE_PRIOR",
    }
    roles_by_component = {
        component: {row["role"] for row in matrix if row["component"] == component}
        for component in expected
    }
    checks = {
        "contract_present": CFG.exists(),
        "parent_f3_1a_exact": cfg["required_parent_commit"] == "f12ffa66deccc0888bc4f97d2bab5a89b2881fd0",
        "five_components_exact": set(components) == expected,
        "candidate_A_every_component": all("CORE_CANDIDATE_A" in roles_by_component[c] for c in expected),
        "challenger_B_every_component": all("CORE_CHALLENGER_B" in roles_by_component[c] for c in expected),
        "reference_every_component": all("REFERENCE_BASELINE" in roles_by_component[c] for c in expected),
        "test_sealed": cfg["test_partition"] == "SEALED" and "zero model-family" in cfg["calibration_role"]["TEST"],
        "formal_g2_not_evaluated": cfg["formal_g2"] == "NOT_EVALUATED",
        "low_n_30": cfg["support_policy"]["min_source_rows_for_direct_conditional_cell"] == 30,
        "silent_pooling_forbidden": cfg["support_policy"]["silent_pooling"] is False,
        "weights_participation": components["DG_PARTICIPATION"]["weight"] == "P_GEW",
        "weights_count": components["DG_TRIP_COUNT"]["weight"] == "P_GEW",
        "weights_time": components["DG_TIME_SCHEDULE"]["weight"] == "W_GEW",
        "weights_distance": components["DG_DISTANCE_PRIOR"]["weight"] == "W_GEW",
        "count_excess_nb": "K_MINUS_1" in components["DG_TRIP_COUNT"]["candidate_A"]["family"],
        "chain_terminal_aware": "TERMINAL_AWARE" in components["DG_ACTIVITY_CHAIN"]["candidate_A"]["family"],
        "time_planned_not_executed": "planned schedule" in components["DG_TIME_SCHEDULE"]["semantic_guardrail"],
        "distance_raw_primary": "RAW_WEGKM" in components["DG_DISTANCE_PRIOR"]["candidate_A"]["family"],
        "llm_out_of_core": any(row["candidate_id"] == "CHAIN_LLM" and row["role"] == "OUT_OF_CORE_EXPERIMENTAL" for row in matrix),
        "rng_five_namespaces": set(cfg["rng_contract"]["namespaces"]) == expected,
        "canonical_candidate_order": "canonical lexical key" in cfg["rng_contract"]["candidate_order"],
        "promotion_thresholds_deferred": any("promotion thresholds" in x for x in cfg["deferred_to_f3_1c"]),
        "decision_register_has_deferred": any(row["state"] == "DEFERRED_TO_F3_1C" for row in decisions),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "counts": {"matrix_rows": len(matrix), "decisions": len(decisions), "components": len(components)},
    }


if __name__ == "__main__":
    import json
    print(json.dumps(verify(), indent=2))
