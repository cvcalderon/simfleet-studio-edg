import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from simfleet_edg.repro import f3_4g2c_joint_real_cal as joint_real
from simfleet_edg.repro.f3_4g2b_joint_real_cal_auth import AuthorizationError

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/f3/f3_4g2c_joint_real_cal_runner_preopen_v1.yaml"
NEGATIVE_AUTH = (
    ROOT / "configs/f3/f3_4g2b_joint_real_cal_authorization_TEMPLATE_v1.json"
)


def load_cfg() -> dict:
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def test_parent_and_zero_cal_state() -> None:
    cfg = load_cfg()
    assert cfg["required_parent_commit"] == (
        "b0ee17a17eb6c58d655b770780cbb40e07b9b33b"
    )
    assert cfg["preopen"]["cal_rows_read"] == 0
    assert cfg["preopen"]["positive_authorization_issued"] is False


def test_exact_eight_hash_bound_inputs_sum_to_6341() -> None:
    cfg = load_cfg()
    keys = (
        "person_day_context",
        "participation",
        "trip_count",
        "chain_days",
        "chain_transitions",
        "time_trips",
        "distance_raw",
        "distance_expanded_sensitivity",
    )
    assert len(keys) == 8
    assert sum(int(cfg["cal_input"][key]["expected_rows"]) for key in keys) == 6341
    assert all(len(str(cfg["cal_input"][key]["sha256"])) == 64 for key in keys)


def test_authorization_precedes_io_and_staging() -> None:
    cfg = load_cfg()
    assert cfg["authorization"]["authorization_before_cal_io"] is True
    assert cfg["authorization"]["authorization_before_staging"] is True


def test_generated_and_observed_weight_semantics_are_frozen() -> None:
    cfg = load_cfg()
    assert cfg["execution"]["generated_trip_evaluation_weight"] == (
        "SOURCE_PERSON_DAY_FIT_WEIGHT_P_GEW"
    )
    assert cfg["execution"]["observed_trip_target_weight"] == "FIT_WEIGHT_W_GEW"


def test_joint_gate_does_not_auto_open_test() -> None:
    cfg = load_cfg()
    assert cfg["joint_gate"]["test_eligibility_may_be_true_after_pass"] is True
    assert cfg["joint_gate"]["explicit_test_open_authorization_in_this_phase"] is False
    assert cfg["preopen"]["test_open_authorized"] is False


def test_count_tvd_identical_is_zero() -> None:
    observed = np.asarray([0, 1, 2, 2, 3], dtype=int)
    weights = np.ones(5, dtype=float)
    assert joint_real._count_tvd(observed, observed.copy(), weights, mobile_only=False) == 0.0


def test_count_mobile_tvd_identical_is_zero() -> None:
    observed = np.asarray([0, 1, 2, 2, 3], dtype=int)
    weights = np.ones(5, dtype=float)
    assert joint_real._count_tvd(observed, observed.copy(), weights, mobile_only=True) == 0.0


def test_metric_matrix_decision_logic(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = pd.DataFrame(
        [
            {
                "metric_id": "A",
                "scope": "X",
                "statistic": "S",
                "max_worsening": 0.1,
                "unit": "u",
                "decision_role": "HARD_GUARDRAIL",
                "source_threshold": "FROZEN",
            },
            {
                "metric_id": "B",
                "scope": "X",
                "statistic": "S",
                "max_worsening": np.nan,
                "unit": "u",
                "decision_role": "REPORT_ONLY",
                "source_threshold": "FROZEN",
            },
        ]
    )
    monkeypatch.setattr(pd, "read_csv", lambda *_args, **_kwargs: fake.copy())
    rows, degradation = joint_real.build_joint_metric_rows(
        {"A": 0.3, "B": 99.0},
        {"A": 0.1, "B": 0.0},
    )
    assert degradation is True
    assert not bool(rows.loc[rows["metric_id"].eq("A"), "gate_pass"].iloc[0])
    assert bool(rows.loc[rows["metric_id"].eq("B"), "gate_pass"].iloc[0])


def test_authorization_rejection_cannot_create_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "joint_real_cal"

    def reject(*_args: object, **_kwargs: object) -> dict:
        raise AuthorizationError("synthetic rejection before CAL I/O")

    monkeypatch.setattr(
        joint_real,
        "load_joint_real_cal_authorization",
        reject,
    )
    with pytest.raises(AuthorizationError):
        joint_real.run_controlled_joint_real_cal(
            ROOT,
            output,
            CFG,
            NEGATIVE_AUTH,
        )
    assert not output.exists()
    assert not Path(f"{output}.partial").exists()


def test_failure_semantics_preserve_partial_after_staging() -> None:
    cfg = load_cfg()
    assert cfg["runbundle"]["preserve_partial_on_failure_after_staging"] is True
    assert cfg["runbundle"]["staging_suffix"] == ".partial"


def test_no_selection_and_test_remains_sealed() -> None:
    cfg = load_cfg()
    assert cfg["execution"]["candidate_selection"] == "NONE"
    assert cfg["preopen"]["test_rows_read"] == 0
    assert cfg["preopen"]["test_open_authorized"] is False
    assert cfg["preopen"]["formal_g2"] == "NOT_EVALUATED"


def test_tracked_auth_template_remains_negative() -> None:
    payload = json.loads(NEGATIVE_AUTH.read_text(encoding="utf-8"))
    assert payload["joint_real_cal_open_authorized"] is False
    assert payload["joint_gate_evaluation_authorized"] is False
