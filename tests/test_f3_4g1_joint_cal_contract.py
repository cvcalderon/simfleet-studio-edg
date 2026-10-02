import csv
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/f3/f3_4g1_joint_cal_contract_freeze_v1.yaml"
REG = ROOT / "configs/f3/f3_4g1_joint_pipeline_registry_v1.json"
MATRIX = ROOT / "docs/F3_4G1_JOINT_METRIC_MATRIX_v1.csv"
WITNESS = ROOT / "docs/F3_4G1_PRIMARY_EVIDENCE_WITNESS_v1.csv"


def load_cfg() -> dict:
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def test_exact_selected_pipeline() -> None:
    cfg = load_cfg()
    assert cfg["entry_state"]["selected_pipeline"] == {
        "DG_PARTICIPATION": "DG_PARTICIPATION::PART_A::PA1",
        "DG_TRIP_COUNT": "DG_TRIP_COUNT::COUNT_REF::REFERENCE",
        "DG_ACTIVITY_CHAIN": "DG_ACTIVITY_CHAIN::CHAIN_A::CHA2",
        "DG_TIME_SCHEDULE": "TIME_B_TB2",
        "DG_DISTANCE_PRIOR": "DIST_REF_REFERENCE",
    }


def test_exact_all_reference_pipeline() -> None:
    cfg = load_cfg()
    assert cfg["entry_state"]["all_reference_pipeline"] == {
        "DG_PARTICIPATION": "DG_PARTICIPATION::PART_REF::REFERENCE",
        "DG_TRIP_COUNT": "DG_TRIP_COUNT::COUNT_REF::REFERENCE",
        "DG_ACTIVITY_CHAIN": "DG_ACTIVITY_CHAIN::CHAIN_REF::REFERENCE",
        "DG_TIME_SCHEDULE": "TIME_REF_REFERENCE",
        "DG_DISTANCE_PRIOR": "DIST_REF_REFERENCE",
    }


def test_cal_rows_are_zero_and_future_total_is_6341() -> None:
    cfg = load_cfg()
    assert cfg["cal_access"]["rows_read_in_f3_4g1"] == 0
    assert cfg["cal_access"]["file_content_read_in_f3_4g1"] is False
    assert cfg["cal_access"]["expected_total_physical_rows_if_opened_once_each"] == 6341


def test_joint_stochastic_protocol_is_frozen() -> None:
    joint = load_cfg()["joint_generation"]
    assert joint["stochastic_replicates"] == 32
    assert joint["common_random_numbers"] is True
    assert joint["master_seed"] == 20260926
    assert joint["same_seed_schedule_across_pipelines"] is True


def test_proper_scores_not_redefined_on_propagated_state() -> None:
    primary = load_cfg()["primary_evidence"]
    assert primary["recompute_proper_scores_on_propagated_generated_state"] is False
    with WITNESS.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 5
    assert all(float(row["selected_minus_reference"]) <= 0.0 for row in rows)


def test_joint_metric_matrix_reuses_frozen_thresholds() -> None:
    with MATRIX.open(newline="", encoding="utf-8") as handle:
        rows = {row["metric_id"]: row for row in csv.DictReader(handle)}
    assert rows["M2-TIME-01"]["max_worsening"] == "0.005"
    assert rows["M2-DIST-01"]["max_worsening"] == "0.25"
    assert rows["DIST-P50"]["max_worsening"] == "0.50"
    assert rows["DIST-P90"]["max_worsening"] == "0.50"
    assert rows["DIST-P95"]["max_worsening"] == "0.50"
    assert rows["DIST-MEAN"]["decision_role"] == "REPORT_ONLY"
    assert rows["M2-DIST-02"]["decision_role"] == "REPORT_ONLY"


def test_registry_has_five_selected_and_five_reference_artifacts() -> None:
    reg = json.loads(REG.read_text(encoding="utf-8"))
    assert len(reg["selected_pipeline"]) == 5
    assert len(reg["all_reference_pipeline"]) == 5
    assert reg["joint_real_cal_open_authorized"] is False
    assert reg["test_open_authorized"] is False


def test_hard_gate_and_boundaries_remain_closed() -> None:
    cfg = load_cfg()
    hard = cfg["hard_gate"]
    assert hard["selected_structural_invariant_violations_required"] == 0
    assert hard["selected_temporal_invariant_violations_required"] == 0
    assert hard["selected_nofuture_violations_required"] == 0
    assert hard["selected_component_dominated_required"] is False
    assert hard["selected_pipeline_material_degradation_required"] is False
    boundary = cfg["boundaries"]
    assert boundary["joint_real_cal_open_authorized"] is False
    assert boundary["joint_gate_evaluated"] is False
    assert boundary["test_open_authorized"] is False
    assert boundary["test_rows_read"] == 0
    assert boundary["formal_g2"] == "NOT_EVALUATED"
