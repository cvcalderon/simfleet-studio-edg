import json
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/f3/f3_4g2g_heldout_test_a1_closure_v1.yaml"
METRICS = ROOT / "docs/F3_4G2G_TEST_METRICS_A1_SNAPSHOT_v1.csv"
EVIDENCE = ROOT / "docs/F3_4G2G_TEST_A1_EVIDENCE_SUMMARY_v1.json"


def load_cfg() -> dict:
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def test_closure_is_g2_pass() -> None:
    cfg = load_cfg()
    assert cfg["status_after_commit"] == "HELDOUT_TEST_A1_CLOSED_G2_PASS"
    assert cfg["formal_g2"]["evaluated"] is True
    assert cfg["formal_g2"]["result"] == "PASS"


def test_execution_identity_exact() -> None:
    source = load_cfg()["source_runbundle"]
    assert source["implementation_commit"] == "911abb2ee194d9c3529880f26ba4773eb82c821d"
    assert source["formal_g2"] == "PASS"
    assert source["holdout_consumed"] is True
    assert source["strict_test_households"] == 260


def test_materialization_summary() -> None:
    cfg = load_cfg()["materialized_test"]
    assert cfg["table_count"] == 8
    assert cfg["source_hash_validation"] == "13/13_PASS"
    assert cfg["train_vocabulary_reused"] is True
    assert cfg["test_vocabulary_fit"] is False


def test_all_decision_metrics_pass() -> None:
    metrics = pd.read_csv(METRICS)
    decision = metrics.loc[metrics["decision_role"].ne("REPORT_ONLY")]
    assert len(metrics) == 17
    assert len(decision) == 14
    assert decision["gate_pass"].astype(bool).all()


def test_three_metrics_are_report_only() -> None:
    metrics = pd.read_csv(METRICS)
    report = metrics.loc[metrics["decision_role"].eq("REPORT_ONLY")]
    assert len(report) == 3


def test_closest_metric_still_has_positive_headroom() -> None:
    cfg = load_cfg()["metric_summary"]["closest_to_threshold"]
    assert cfg["metric_id"] == "M2-CHAIN-01"
    assert float(cfg["headroom"]) > 0.0
    assert float(cfg["worsening"]) < float(cfg["max_worsening"])


def test_hard_invariants_zero() -> None:
    g2 = load_cfg()["formal_g2"]
    assert g2["structural_invariant_violations"] == 0
    assert g2["temporal_invariant_violations"] == 0
    assert g2["nofuture_violations"] == 0


def test_holdout_is_terminally_consumed() -> None:
    boundary = load_cfg()["holdout_boundary"]
    assert boundary["consumed"] is True
    assert boundary["same_holdout_rerun_authorized"] is False
    assert boundary["post_test_tuning_authorized"] is False
    assert boundary["same_authorization_rerun_authorized"] is False
    assert boundary["result_is_terminal_for_this_holdout"] is True


def test_evidence_summary_matches() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert evidence["formal_g2"] == "PASS"
    assert evidence["strict_test_households"] == 260
    assert evidence["source_hash_validation_pass"] == 13
    assert evidence["pipeline_artifact_slots"] == 10


def test_g1_remains_open() -> None:
    note = load_cfg()["project_gate_note"]
    assert note["formal_g1"] == "OPEN"
    assert note["heldout_g2"] == "PASS"
