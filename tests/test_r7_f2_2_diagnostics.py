from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import yaml

from simfleet_edg.common.diagnostic_metrics import (
    total_variation_distance,
    wasserstein_1d,
    weighted_distribution,
    weighted_mean,
    weighted_quantile,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "reproduction" / "r7_f2_2_diagnostics.yaml"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_weighted_mean() -> None:
    assert weighted_mean([1, 3], [1, 3]) == 2.5


def test_weighted_distribution_and_tvd() -> None:
    left = weighted_distribution(pd.Series(["a", "b"]), pd.Series([1.0, 1.0]))
    right = weighted_distribution(pd.Series(["a", "a"]), pd.Series([1.0, 1.0]))
    assert abs(float(left.sum()) - 1.0) < 1e-12
    assert abs(float(right.sum()) - 1.0) < 1e-12
    assert total_variation_distance(left, right) == 0.5


def test_weighted_quantile_uses_inverse_cdf() -> None:
    assert weighted_quantile([1, 2, 3], [1, 1, 8], 0.5) == 3.0


def test_wasserstein_1d_simple_shift() -> None:
    value = wasserstein_1d([0, 1], [1, 1], [1, 2], [1, 1])
    assert abs(value - 1.0) < 1e-12


def test_r7_frozen_anchors() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    expected = config["expected"]
    assert expected["validation_pass"] == 18
    assert expected["validation_total"] == 18
    assert expected["strict_train_person_days"] == 2200
    assert expected["ref_train_binary_rows"] == 2154
    assert expected["ref_train_core_strict_count_rows"] == 2052
    assert expected["ref_train_direct_purpose_rows"] == 6134
    assert expected["ref_train_direct_time_rows"] == 6103
    assert expected["ref_train_transition_rows"] == 5812
    assert expected["ref_train_distance_raw_rows"] == 5617
    assert expected["ref_train_distance_expanded_rows"] == 6145
    assert expected["ref_train_full_functional_rows"] == 1422
    assert expected["full_day_donors"] == 1658
    assert expected["replay_participation_coverage"] == 87591
    assert expected["replay_count_coverage"] == 82873


def test_r7_no_future_and_gate_policies() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    policies = config["policies"]
    assert policies["strict_train_reference_only"] is True
    assert policies["calibration_test_outcomes_forbidden"] is True
    assert policies["person_reference_weight"] == "P_GEW"
    assert policies["trip_reference_weight"] == "W_GEW"
    assert policies["no_mode_metric"] is True
    assert policies["km_routing_forbidden"] is True
    assert policies["low_n_threshold"] == 30
    assert policies["low_n_action"] == "FLAG_NOT_POOL"
    assert policies["selection_bias_diagnostic_only"] is True
    assert policies["numeric_g2_thresholds_frozen"] is False
    assert policies["formal_g2_evaluated"] is False


def test_historical_witness_hashes_match_config() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    witness_dir = ROOT / config["historical_witness_dir"]
    assert len(config["historical_artifacts"]) == 11
    for filename, spec in config["historical_artifacts"].items():
        path = witness_dir / filename
        assert path.is_file(), filename
        assert _sha256(path) == spec["sha256"], filename


def test_global_metrics_is_documented_numeric_equivalence() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    spec = config["historical_artifacts"]["simfleet_edg_F2_2_global_metrics_v1.csv"]
    assert spec["comparison"] == "NUMERIC_EQUIVALENT"
    assert float(spec["atol"]) == 1e-12
