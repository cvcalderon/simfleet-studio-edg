from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from simfleet_edg.evaluation.cal_metrics import wasserstein_1d, weighted_mean, weighted_quantile
from simfleet_edg.evaluation.distance_prior_adapter import DistancePriorAdapter

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/f3/f3_4f2a_distance_prior_synthetic_preopen_v1.yaml"


def test_synthetic_preopen_never_opens_cal_or_test() -> None:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    assert cfg["boundaries"]["cal_rows_read"] == 0
    assert cfg["boundaries"]["cal_files_read"] == []
    assert cfg["boundaries"]["real_distance_prior_cal_open_authorized"] is False
    assert cfg["boundaries"]["test_rows_read"] == 0
    assert cfg["boundaries"]["test_open_authorized"] is False


def test_candidate_selection_remains_none() -> None:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    assert cfg["candidate_registry"]["expected_candidates"] == 5
    assert cfg["boundaries"]["candidate_selection"] == "NONE"
    assert cfg["synthetic_metric_smoke"]["selection_authorized"] is False
    assert cfg["summary_smoke"]["synthetic_guardrail_decision_authorized"] is False


def test_crn_contract_is_candidate_independent() -> None:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    assert cfg["synthetic_protocol"]["stochastic_replicates"] == 32
    assert cfg["synthetic_protocol"]["candidate_identity_in_rng_key"] is False
    assert cfg["synthetic_protocol"]["rng_namespace"] == "DG_DISTANCE_PRIOR::TRIP::1"


def test_mean_role_and_quantile_tolerance_preserved() -> None:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    assert cfg["summary_smoke"]["mean_role"] == "REPORT_ONLY_UNTHRESHOLDED"
    assert cfg["summary_smoke"]["quantile_tolerance_km_frozen_for_future_real_cal"] == 0.50


def test_synthetic_observed_vector_has_32_positive_finite_values() -> None:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    values = np.asarray(cfg["synthetic_metric_smoke"]["synthetic_observed_distance_km"], dtype=float)
    assert len(values) == 32
    assert np.isfinite(values).all()
    assert (values > 0).all()


def test_wasserstein_smoke_identity_and_shift() -> None:
    values = np.asarray([1.0, 2.0, 3.0])
    weights = np.ones(3)
    assert wasserstein_1d(values, weights, values.copy(), weights) == 0.0
    assert wasserstein_1d(values, weights, values + 1.0, weights) == pytest.approx(1.0)


def test_weighted_summary_primitives_are_finite() -> None:
    values = np.asarray([1.0, 2.0, 3.0, 4.0])
    weights = np.ones(4)
    assert weighted_mean(values, weights) == pytest.approx(2.5)
    assert weighted_quantile(values, weights, 0.50) == 2.0
    assert weighted_quantile(values, weights, 0.90) == 4.0
    assert weighted_quantile(values, weights, 0.95) == 4.0


def test_distance_adapter_rejects_multirow_without_sampling(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = object.__new__(DistancePriorAdapter)
    with pytest.raises(ValueError, match="exactly one row"):
        adapter.sample_one(pd.DataFrame([{"x": 1}, {"x": 2}]), seed=1)


def test_downstream_boundaries_remain_closed() -> None:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    assert cfg["boundaries"]["joint_cal_gate_authorized"] is False
    assert cfg["boundaries"]["test_open_authorized"] is False
    assert cfg["boundaries"]["formal_g2"] == "NOT_EVALUATED"
