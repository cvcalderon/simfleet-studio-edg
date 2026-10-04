from pathlib import Path

import yaml


def test_impl01_config_freezes_expected_sources_and_anchors() -> None:
    root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load((root / "configs/f1/f1_pconstr_impl01_reconciliation_v1.yaml").read_text())
    assert set(config["sources"]) == {
        "1000A-1029", "1000A-2070", "1000A-2071", "1000A-3082", "5000H-1001"
    }
    assert config["expected_reconciliation"] == {
        "bezirk_count": 12,
        "detail_cells": 1584,
        "detail_cells_changed": 56,
        "stage1_l1_total": 161,
        "stage2_l1_total": 272,
        "stage3_l1_total": 478,
        "max_detailed_abs_adjustment": 12,
        "all_bezirke_feasible": True,
    }
    assert config["reconciliation"]["stage4_tie_break"] == "CANONICAL_WEIGHTED_LINEAR_V1"
    assert config["boundaries"]["calibration_read"] is False
    assert config["boundaries"]["test_read"] is False
    assert config["boundaries"]["six_plus_completion"] == "deferred_to_IMPL_02"
