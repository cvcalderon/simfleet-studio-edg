from __future__ import annotations

import ast
from pathlib import Path

from simfleet_edg.repro.f4_1d_runtime_dgen_binding import precheck

ROOT = Path(__file__).resolve().parents[1]


def test_runner_static_precheck_without_large_inputs(tmp_path: Path) -> None:
    result = precheck(
        ROOT,
        ROOT / "configs/f4/f4_1d_runtime_dgen_binding_preopen_v1.yaml",
        tmp_path,
        post_push_git=False,
        check_large_inputs=False,
    )
    assert result["status"] == "PASS"


def test_runtime_implementation_does_not_import_spatial_or_synthetic_cohort() -> None:
    paths = [
        ROOT / "src/simfleet_edg/demand/runtime_context.py",
        ROOT / "src/simfleet_edg/demand/runtime_generator.py",
        ROOT / "src/simfleet_edg/repro/f4_1d_runtime_dgen_binding.py",
    ]
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        assert not any(name.startswith("simfleet_edg.spatial") for name in imports)
        assert "simfleet_edg.repro.f3_4g2a_joint_synthetic" not in imports
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "make_synthetic_cohort" not in text
    assert "CAL_SCENARIO_ID" not in text


def test_runner_marks_smoke_as_not_downstream_authorized() -> None:
    text = (ROOT / "src/simfleet_edg/repro/f4_1d_runtime_dgen_binding.py").read_text(
        encoding="utf-8"
    )
    assert '"downstream_authorized": False' in text
    assert '"full_100k_dgen_realization": False' in text
