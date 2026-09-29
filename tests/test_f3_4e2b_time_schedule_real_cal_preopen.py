from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import yaml

from simfleet_edg.evaluation import time_schedule_cal_real as real

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/f3/f3_4e2b_time_schedule_real_cal_preopen_v1.yaml"


def test_preopen_contract_is_closed() -> None:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert cfg["phase"] == "F3.4e-2b"
    assert cfg["component"] == "DG_TIME_SCHEDULE"
    assert cfg["required_parent_commit"] == "fc238749d5972ee189f3223affd8f4daa9f2b186"
    assert cfg["cal_input"]["expected_physical_rows"] == 1712
    assert cfg["cal_input"]["expected_fixed_cohort_days"] == 378
    assert cfg["cal_input"]["expected_isolated_time_rows"] == 1243
    assert cfg["evaluation"]["primary_metric"] == "M2-TIME-01"
    assert cfg["evaluation"]["practical_margin"] == 0.005
    assert cfg["evaluation"]["stochastic_replicates"] == 32
    assert cfg["evaluation"]["household_bootstrap_replicates"] == 1000
    assert cfg["preopen"]["cal_rows_read"] == 0
    assert cfg["preopen"]["candidate_selection"] == "NONE"
    assert cfg["preopen"]["real_time_schedule_cal_open_authorized"] is False
    assert cfg["preopen"]["distance_prior_real_cal_authorized"] is False
    assert cfg["preopen"]["test_open_authorized"] is False
    assert cfg["preopen"]["formal_g2"] == "NOT_EVALUATED"


def test_authorization_template_is_non_executable() -> None:
    payload = json.loads((ROOT / "docs/F3_4E2B_EXECUTION_AUTHORIZATION_TEMPLATE_v1.json").read_text(encoding="utf-8"))
    assert payload["real_time_schedule_cal_open_authorized"] is False
    assert payload["candidate_artifacts"] == 7
    assert payload["candidate_selection_at_entry"] == "NONE"
    assert set(payload["allowed_cal_files"]) == {"person_day_context.csv", "time_trips.csv"}
    assert payload["distance_prior_real_cal_authorized"] is False
    assert payload["test_open_authorized"] is False
    assert payload["formal_g2"] == "NOT_EVALUATED"


def test_false_authorization_fails_before_git_or_cal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({
        "phase": "F3.4e-2b",
        "component": "DG_TIME_SCHEDULE",
        "authorized_implementation_commit": "unused",
        "real_time_schedule_cal_open_authorized": False,
        "candidate_artifacts": 7,
        "candidate_selection_at_entry": "NONE",
        "allowed_cal_files": ["person_day_context.csv", "time_trips.csv"],
        "distance_prior_real_cal_authorized": False,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
    }), encoding="utf-8")
    monkeypatch.setattr(real, "_git", lambda *_args: pytest.fail("git must not run"))
    with pytest.raises(PermissionError, match="real_time_schedule_cal_open_authorized"):
        real.load_authorization(auth, tmp_path)


def test_invalid_authorization_creates_no_partial_runbundle(tmp_path: Path) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({
        "phase": "F3.4e-2b",
        "component": "DG_TIME_SCHEDULE",
        "real_time_schedule_cal_open_authorized": False,
    }), encoding="utf-8")
    out = tmp_path / "run"
    with pytest.raises(PermissionError):
        real.run_controlled_time_schedule_cal(ROOT, out, CONFIG, auth, write_stochastic_evidence=False)
    assert not out.exists()
    assert not out.with_name("run.partial").exists()


def test_trips_remaining_mapping_does_not_assume_trip_id_ordinal() -> None:
    assert real._trips_remaining_after_current("SINGLE") == 0
    assert real._trips_remaining_after_current("LAST") == 0
    assert real._trips_remaining_after_current("FIRST") == 1
    assert real._trips_remaining_after_current("MIDDLE") == 1
    with pytest.raises(ValueError):
        real._trips_remaining_after_current("UNKNOWN")


def test_time_seed_is_candidate_independent() -> None:
    a = real._time_seed("context-1", "trip-X", 7)
    b = real._time_seed("context-1", "trip-X", 7)
    assert a == b
    assert a != real._time_seed("context-1", "trip-Y", 7)


def test_weighted_hour_tvd_known_values() -> None:
    observed = np.array([8, 8, 9, 9])
    generated_same = np.array([8, 8, 9, 9])
    generated_shift = np.array([10, 10, 11, 11])
    weight = np.ones(4)
    assert real._weighted_hour_tvd(observed, generated_same, weight) == 0.0
    assert real._weighted_hour_tvd(observed, generated_shift, weight) == 1.0


def test_circular_wasserstein_identical_is_zero() -> None:
    values = np.array([0, 60, 1439])
    weights = np.array([1.0, 2.0, 1.0])
    assert real._circular_wasserstein_minutes(values, values.copy(), weights) == 0.0


def test_downstream_boundaries_remain_closed() -> None:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert cfg["preopen"]["distance_prior_real_cal_authorized"] is False
    assert cfg["preopen"]["test_open_authorized"] is False
    assert cfg["preopen"]["formal_g2"] == "NOT_EVALUATED"
