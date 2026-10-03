from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/f3/f3_4g2d_joint_cal_a1_closure_v1.yaml"
METRICS = ROOT / "docs/F3_4G2D_JOINT_METRICS_A1_SNAPSHOT_v1.csv"


def load_cfg() -> dict:
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def test_joint_a1_is_closed_pass() -> None:
    cfg = load_cfg()
    assert cfg["status_after_commit"] == "JOINT_CAL_A1_CLOSED_PASS"
    assert cfg["joint_gate"]["evaluated"] is True
    assert cfg["joint_gate"]["pass"] is True
    assert cfg["joint_gate"]["reasons"] == []


def test_execution_identity_and_volume_are_exact() -> None:
    source = load_cfg()["source_runbundle"]
    assert source["implementation_commit"] == (
        "beeb79a79e81aaaff3041542c3a9f3c08937e1dc"
    )
    assert source["cal_rows_read_total_physical"] == 6341
    assert source["generated_day_rows"] == 30016
    assert source["generated_trip_rows"] == 97134
    assert source["stochastic_replicates"] == 32
    assert source["pipeline_artifact_slots"] == 10
    assert source["candidate_selection"] == "NONE"


def test_all_decision_metrics_pass() -> None:
    metrics = pd.read_csv(METRICS)
    decision = metrics.loc[metrics["decision_role"].ne("REPORT_ONLY")]
    assert len(metrics) == 17
    assert len(decision) == 14
    assert decision["gate_pass"].astype(bool).all()


def test_exactly_three_metrics_are_report_only() -> None:
    metrics = pd.read_csv(METRICS)
    report = set(
        metrics.loc[
            metrics["decision_role"].eq("REPORT_ONLY"),
            "metric_id",
        ].astype(str)
    )
    assert report == {"TIME-CIRCULAR-W1", "DIST-MEAN", "M2-DIST-02"}


def test_only_two_decision_metrics_worsen() -> None:
    metrics = pd.read_csv(METRICS)
    decision = metrics.loc[metrics["decision_role"].ne("REPORT_ONLY")]
    worsened = decision.loc[
        decision["selected_minus_reference_worsening"].astype(float) > 0,
        "metric_id",
    ].astype(str).tolist()
    assert worsened == ["M2-COUNT-01", "DIST-P50"]


def test_positive_worsening_metrics_have_headroom() -> None:
    metrics = pd.read_csv(METRICS).set_index("metric_id")
    for metric_id in ("M2-COUNT-01", "DIST-P50"):
        row = metrics.loc[metric_id]
        assert float(row["selected_minus_reference_worsening"]) < float(
            row["max_worsening"]
        )


def test_hard_invariants_zero() -> None:
    gate = load_cfg()["joint_gate"]
    assert gate["structural_invariant_violations"] == 0
    assert gate["temporal_invariant_violations"] == 0
    assert gate["nofuture_violations"] == 0
    assert gate["selected_component_dominated"] is False
    assert gate["selected_pipeline_material_degradation"] is False


def test_test_is_eligible_but_not_open() -> None:
    boundary = load_cfg()["test_boundary"]
    assert boundary["test_eligible_by_joint_gate"] is True
    assert boundary["test_open_authorized"] is False
    assert boundary["test_rows_read"] == 0
    assert boundary["explicit_main_authorization_required_before_test_open"] is True


def test_g2_remains_not_evaluated() -> None:
    assert load_cfg()["formal_g2"] == "NOT_EVALUATED"
