from pathlib import Path

from simfleet_edg.spatial.candidate_policies import POLICIES


def test_v1_candidates_are_fixed_and_attractiveness_is_only_ablation() -> None:
    assert POLICIES == ("S_NEAR", "S_DIST", "S_ATTR")
    code = (Path(__file__).resolve().parents[1] /
            "src/simfleet_edg/repro/f4_2a_core_spatial.py").read_text()
    assert '"g3_opened": False' in code
    assert "candidate_promotable_internal_only" in code
    assert "postpush_gate(repo)" in code
    assert "SCENARIO_ID = \"F4_2A_CORE_REFERENCE_V1\"" in code
