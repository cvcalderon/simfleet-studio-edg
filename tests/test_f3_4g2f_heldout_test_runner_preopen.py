import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from simfleet_edg.repro import f3_4g2f_heldout_test_runner as test_runner
from simfleet_edg.repro.f3_4g2e_test_auth import (
    TestAuthorizationError as HeldoutAuthorizationError,
)

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/f3/f3_4g2f_heldout_test_runner_preopen_v1.yaml"
NEGATIVE = ROOT / "configs/f3/f3_4g2e_test_authorization_TEMPLATE_v1.json"
VOCAB = ROOT / "configs/f3/f3_4g2f_train_vocabulary_snapshot_v1.json"
SPLIT = ROOT / "artifacts/runs/R2_eligibility_split_v1/split_manifest_reproduced.csv"


def load_cfg() -> dict:
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def test_parent_and_zero_test_state() -> None:
    cfg = load_cfg()
    assert cfg["required_parent_commit"] == (
        "18a8b7921b7af14d7cd6f31e37a6624f4ac551b1"
    )
    assert cfg["preopen"]["test_outcome_rows_read"] == 0
    assert cfg["preopen"]["test_materialized"] is False
    assert cfg["preopen"]["holdout_consumed"] is False


def test_exact_strict_test_households() -> None:
    split = pd.read_csv(SPLIT)
    households = test_runner._test_households(split)
    assert len(households) == 260


def test_original_materializer_is_not_modified_for_test() -> None:
    cfg = load_cfg()["materializer_reuse"]
    assert cfg["original_train_cal_contract_remains_unchanged"] is True
    assert cfg["original_test_forbidden_rule_remains_unchanged"] is True
    assert cfg["test_materialization_uses_separate_commit_bound_runner"] is True


def test_frozen_vocabulary_is_train_fitted() -> None:
    vocabulary = json.loads(VOCAB.read_text(encoding="utf-8"))
    assert vocabulary["fit_partition"] == "TRAIN"
    assert vocabulary["unseen_token"] == "__UNSEEN__"


def test_test_unseen_category_maps_to_unseen() -> None:
    vocabulary = {
        "fit_partition": "TRAIN",
        "unseen_token": "__UNSEEN__",
        "datasets": {
            "person_day_context": {
                "sex": {
                    "vocabulary": [
                        "MALE",
                        "FEMALE",
                        "__UNSEEN__",
                    ]
                }
            }
        },
    }
    tables = {
        name: pd.DataFrame()
        for name in test_runner.DATASETS
    }
    tables["person_day_context"] = pd.DataFrame(
        {"sex": ["MALE", "NEW_TEST_ONLY"]}
    )
    report = test_runner.apply_frozen_train_vocabulary(
        tables,
        vocabulary,
    )
    assert tables["person_day_context"]["sex"].tolist() == [
        "MALE",
        "__UNSEEN__",
    ]
    assert report["datasets"]["person_day_context"]["sex"][
        "test_unseen_count"
    ] == 1


def test_test_seed_is_distinct_and_frozen() -> None:
    execution = load_cfg()["execution"]
    assert execution["scenario_id"] == "TEST_EVAL_V1"
    assert execution["master_seed"] == 20261003
    assert execution["stochastic_replicates"] == 32


def test_no_selection_or_post_test_tuning() -> None:
    execution = load_cfg()["execution"]
    assert execution["candidate_selection"] == "NONE"
    assert execution["post_test_tuning"] == "FORBIDDEN"
    assert execution["teacher_forcing"] is False


def test_consumption_marker_tracks_first_content_read() -> None:
    consumption = load_cfg()["holdout_consumption"]
    assert consumption[
        "marker_written_immediately_after_first_source_content_block_read"
    ] is True
    assert consumption["consumed_trigger"] == (
        "FIRST_PROTECTED_SOURCE_CONTENT_BLOCK_READ"
    )
    assert consumption["same_holdout_rerun_after_consumption"] is False


def test_g2_pass_rule() -> None:
    metrics = pd.DataFrame(
        [
            {
                "metric_id": f"M{i}",
                "decision_role": "HARD_GUARDRAIL",
                "gate_pass": True,
            }
            for i in range(14)
        ]
        + [
            {
                "metric_id": f"R{i}",
                "decision_role": "REPORT_ONLY",
                "gate_pass": True,
            }
            for i in range(3)
        ]
    )
    decision = test_runner._g2_decision(
        metrics,
        structural=0,
        temporal=0,
        nofuture=0,
        artifact_manifests_frozen=True,
    )
    assert decision["formal_g2"] == "PASS"


def test_g2_scientific_fail_is_valid_terminal_result() -> None:
    metrics = pd.DataFrame(
        [
            {
                "metric_id": f"M{i}",
                "decision_role": "HARD_GUARDRAIL",
                "gate_pass": i != 0,
            }
            for i in range(14)
        ]
        + [
            {
                "metric_id": f"R{i}",
                "decision_role": "REPORT_ONLY",
                "gate_pass": True,
            }
            for i in range(3)
        ]
    )
    decision = test_runner._g2_decision(
        metrics,
        structural=0,
        temporal=0,
        nofuture=0,
        artifact_manifests_frozen=True,
    )
    assert decision["formal_g2"] == "FAIL"
    assert decision["scientific_fail_is_valid_execution"] is True
    assert decision["same_holdout_rerun_authorized"] is False


def test_negative_authorization_precedes_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "heldout_test"

    def reject(*_args: object, **_kwargs: object) -> dict:
        raise HeldoutAuthorizationError(
            "synthetic rejection before TEST outcome I/O"
        )

    monkeypatch.setattr(
        test_runner,
        "load_heldout_test_authorization",
        reject,
    )
    with pytest.raises(HeldoutAuthorizationError):
        test_runner.run_controlled_heldout_test(
            ROOT,
            output,
            CFG,
            NEGATIVE,
        )
    assert not output.exists()
    assert not Path(f"{output}.partial").exists()


def test_metric_matrix_shape_contract() -> None:
    cfg = load_cfg()["metrics"]
    assert cfg["total"] == 17
    assert cfg["decision"] == 14
    assert cfg["report_only"] == 3
    assert cfg["no_composite_score"] is True


def test_same_holdout_rerun_is_never_authorized_after_consumption() -> None:
    cfg = load_cfg()
    assert cfg["holdout_consumption"][
        "same_holdout_rerun_after_consumption"
    ] is False
    assert cfg["formal_g2"][
        "valid_scientific_fail_is_terminal_on_same_holdout"
    ] is True


def test_preopen_g2_not_evaluated() -> None:
    assert load_cfg()["preopen"]["formal_g2"] == "NOT_EVALUATED"
