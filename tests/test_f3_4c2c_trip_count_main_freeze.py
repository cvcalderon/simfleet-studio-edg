from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import yaml

CFG = Path("configs/f3/f3_4c2c_trip_count_main_freeze_v1.yaml")
SCRIPT = Path("scripts/verify_f3_4c2c_main_freeze.py")


def _module():
    spec = importlib.util.spec_from_file_location("f3_4c2c_verifier", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_freeze_contract_selects_reference():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    assert cfg["selection"]["artifact_id"] == (
        "DG_TRIP_COUNT::COUNT_REF::REFERENCE"
    )
    assert cfg["selection"]["target_state_after_commit"] == "MAIN_FROZEN"


def test_freeze_does_not_authorize_next_execution_or_test():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    assert (
        cfg["selection"]["authorized_for_downstream_component_execution"]
        is False
    )
    assert cfg["boundaries"]["test_open_authorized"] is False
    assert cfg["boundaries"]["next_component_authorized"] is False
    assert cfg["boundaries"]["formal_g2"] == "NOT_EVALUATED"


def test_count_observability_cardinalities_remain_frozen():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    ev = cfg["cal_evidence"]
    assert ev["physical_rows_read"] == 1310
    assert ev["participation_rows"] == 460
    assert ev["observed_tripday_rows"] == 399
    assert ev["known_notrip_rows"] == 61
    assert ev["isolated_rows"] == 381
    assert ev["count_target_observed_tripday_rows"] == 381
    assert ev["count_target_unobserved_tripday_rows"] == 18
    assert ev["count_guardrail_person_days"] == 442


def test_empty_csv_helper_accepts_no_decision_evidence(tmp_path: Path):
    module = _module()
    path = tmp_path / "empty.csv"
    path.write_text("\n", encoding="utf-8")
    frame = module.read_csv_allow_empty(path)
    assert isinstance(frame, pd.DataFrame)
    assert frame.empty


def test_decision_basis_records_no_eligible_challenger():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    basis = cfg["decision_basis"]
    assert basis["eligible_family_winners"] == 0
    assert basis["promotion_decision_rows"] == 0
    assert basis["bootstrap_rows"] == 0
    assert basis["challengers_failed_isolated_guardrails"] is True
    assert basis["propagated_interpretation"] == "REFERENCE_SELF_CHECK_ONLY"
