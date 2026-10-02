from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run = args.run_dir
    manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
    selected = json.loads((run / "selected_component_artifact.json").read_text(encoding="utf-8"))
    validation = pd.read_csv(run / "validation.csv")
    checksums = {}
    for line in (run / "checksums.sha256").read_text(encoding="utf-8").splitlines():
        if line.strip():
            h, name = line.split(maxsplit=1)
            checksums[name.strip()] = h
    checksum_ok = all((run/name).is_file() and sha256(run/name) == h for name, h in checksums.items())
    checks = {
        "status_pass": manifest.get("status") == "PASS",
        "phase_exact": manifest.get("phase") == "F3.4f-2b",
        "candidate_artifacts_5": manifest.get("candidate_artifacts") == 5,
        "cal_rows_2873": manifest.get("cal_rows_read_total_physical") == 2873,
        "isolated_rows_1147": manifest.get("cal_isolated_raw_rows") == 1147,
        "sensitivity_rows_1257": manifest.get("cal_sensitivity_rows") == 1257,
        "joint_not_authorized": manifest.get("joint_cal_gate_authorized") is False,
        "test_zero": manifest.get("test_rows_read") == 0,
        "test_sealed": manifest.get("test_open_authorized") is False,
        "g2_not_evaluated": manifest.get("formal_g2") == "NOT_EVALUATED",
        "selected_not_downstream_authorized": selected.get("authorized_for_downstream") is False,
        "validation_all_pass": bool(validation["status"].eq("PASS").all()),
        "checksums_ok": checksum_ok,
    }
    failed = [k for k,v in checks.items() if not v]
    payload = {"phase":"F3.4f-2b","component":"DG_DISTANCE_PRIOR","status":"PASS" if not failed else "FAIL","runbundle_gate":"PASS" if not failed else "FAIL","checks":checks,"failed":failed,"proposed_selected_artifact_id":manifest.get("proposed_selected_artifact_id"),"formal_g2":"NOT_EVALUATED","test_rows_read":0}
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
