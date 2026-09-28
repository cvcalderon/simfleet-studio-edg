from pathlib import Path


def test_freeze_config_mentions_exact_selection():
    p = Path("configs/f3/f3_4b2c_participation_main_freeze_v1.yaml")
    t = p.read_text(encoding="utf-8")
    assert "DG_PARTICIPATION::PART_A::PA1" in t
    assert "state: MAIN_FROZEN" in t
    assert "open_authorized: false" in t
    assert "formal_g2: NOT_EVALUATED" in t


def test_witness_manifest_has_required_files():
    p = Path("docs/F3_4B2C_RUNBUNDLE_WITNESSES_v1.sha256")
    lines = [x for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    names = {line.split("  ", 1)[1] for line in lines}
    required = {
        "checksums.sha256",
        "run_manifest.json",
        "evidence_manifest.json",
        "execution_authorization_snapshot.json",
        "input_hash_validation.csv",
        "primary_metrics.csv",
        "grid_selection.csv",
        "promotion_decisions.csv",
        "bootstrap_intervals.csv",
        "guardrails.csv",
        "selected_component_artifact.json",
        "part_b_calibration_decision.json",
    }
    assert names == required


def test_precommit_verifier_allows_exact_untracked_overlay():
    p = Path("scripts/verify_f3_4b2c_main_freeze.py")
    t = p.read_text(encoding="utf-8")
    assert '"no_tracked_worktree_changes"' in t
    assert '"no_staged_changes"' in t
    assert '"overlay_scope_exact"' in t
    assert '"worktree_clean"' not in t
