from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from simfleet_edg.evaluation import distance_prior_cal_real as real

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/f3/f3_4f2b_distance_prior_real_cal_preopen_v1.yaml"


def test_preopen_contract_is_closed() -> None:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert cfg["phase"] == "F3.4f-2b"
    assert cfg["required_parent_commit"] == "47a95201cea51d4e856acbb90a3a3e49e1cb9a5a"
    assert cfg["cal_input"]["expected_physical_rows"] == 2873
    assert cfg["evaluation"]["primary_metric"] == "M2-DIST-01"
    assert cfg["evaluation"]["practical_margin_km"] == 0.25
    assert cfg["evaluation"]["stochastic_replicates"] == 32
    assert cfg["evaluation"]["household_bootstrap_replicates"] == 1000
    assert cfg["summary_guardrails"]["max_worsening_km"] == 0.50
    assert cfg["preopen"]["cal_rows_read"] == 0
    assert cfg["preopen"]["candidate_selection"] == "NONE"
    assert cfg["preopen"]["real_distance_prior_cal_open_authorized"] is False
    assert cfg["preopen"]["joint_cal_gate_authorized"] is False
    assert cfg["preopen"]["test_open_authorized"] is False


def test_authorization_template_is_non_executable() -> None:
    payload = json.loads((ROOT / "docs/F3_4F2B_EXECUTION_AUTHORIZATION_TEMPLATE_v1.json").read_text(encoding="utf-8"))
    assert payload["real_distance_prior_cal_open_authorized"] is False
    assert payload["candidate_artifacts"] == 5
    assert payload["candidate_selection_at_entry"] == "NONE"
    assert set(payload["allowed_cal_files"]) == {"person_day_context.csv", "distance_raw.csv", "distance_expanded_sensitivity.csv"}
    assert payload["joint_cal_gate_authorized"] is False
    assert payload["test_open_authorized"] is False


def test_false_authorization_fails_before_git_or_cal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"phase":"F3.4f-2b","component":"DG_DISTANCE_PRIOR","authorized_implementation_commit":"unused","real_distance_prior_cal_open_authorized":False,"candidate_artifacts":5,"candidate_selection_at_entry":"NONE","allowed_cal_files":["person_day_context.csv","distance_raw.csv","distance_expanded_sensitivity.csv"],"joint_cal_gate_authorized":False,"test_open_authorized":False,"formal_g2":"NOT_EVALUATED"}), encoding="utf-8")
    monkeypatch.setattr(real, "_git", lambda *a, **k: (_ for _ in ()).throw(AssertionError("git must not be called")))
    with pytest.raises(PermissionError):
        real.load_authorization(auth, tmp_path)


def test_distance_seed_is_deterministic_and_candidate_free() -> None:
    a = real._distance_seed("ctx", 7, 3)
    b = real._distance_seed("ctx", 7, 3)
    assert a == b
    assert a != real._distance_seed("ctx", 8, 3)
    assert a != real._distance_seed("ctx", 7, 4)


def test_quantile_guardrail_worsening_semantics() -> None:
    incumbent = {"MEAN":1.0,"P50":1.0,"P90":2.0,"P95":3.0}
    challenger = {"MEAN":9.0,"P50":1.5,"P90":2.49,"P95":3.5}
    passed, row = real._compare_quantile_guardrails(incumbent, challenger)
    assert passed
    assert row["mean_role"] == "REPORT_ONLY_UNTHRESHOLDED"
    challenger["P90"] = 2.5001
    passed, _ = real._compare_quantile_guardrails(incumbent, challenger)
    assert not passed


def test_summary_errors_zero_for_identical_replicates() -> None:
    observed = np.array([1.0,2.0,4.0,8.0])
    weights = np.array([1.0,2.0,1.0,1.0])
    generated = np.repeat(observed[None,:], real.REPLICATES, axis=0)
    out = real._summary_errors(observed, generated, weights)
    assert all(abs(v) < 1e-12 for v in out.values())


def test_metric_mean32_zero_for_identical_replicates() -> None:
    observed = np.array([1.0,2.0,4.0])
    weights = np.ones(3)
    generated = np.repeat(observed[None,:], real.REPLICATES, axis=0)
    assert real._metric_mean32(observed, generated, weights) == 0.0


def test_merge_distance_requires_context_resolution() -> None:
    context = pd.DataFrame([{"row_id":"a","source_household_id":1,"source_person_id":2,"fit_weight_P_GEW":1.0}])
    frame = pd.DataFrame([{"context_row_id":"missing","source_household_id":1,"source_person_id":2,"source_trip_id":1,"fit_weight_W_GEW":1.0,"target_distance_prior_km":1.0}])
    with pytest.raises(ValueError, match="resolve"):
        real._merge_distance(context, frame)


def test_downstream_boundaries_remain_closed() -> None:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert cfg["preopen"]["joint_cal_gate_authorized"] is False
    assert cfg["preopen"]["test_open_authorized"] is False
    assert cfg["preopen"]["formal_g2"] == "NOT_EVALUATED"
