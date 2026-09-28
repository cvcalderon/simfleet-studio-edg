from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

WITNESS_FILES = [
    "checksums.sha256",
    "run_manifest.json",
    "evidence_manifest.json",
    "execution_authorization_snapshot.json",
    "input_hash_validation.csv",
    "primary_metrics.csv",
    "grid_selection.csv",
    "promotion_decisions.csv",
    "bootstrap_intervals.csv",
    "isolated_guardrails.csv",
    "propagated_guardrails.csv",
    "selected_component_artifact.json",
    "stochastic_evidence.csv.gz",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def checksum_manifest_pass(run: Path) -> bool:
    for line in (run / "checksums.sha256").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, rel = line.split(maxsplit=1)
        if sha256(run / rel.strip()) != digest:
            return False
    return True


def read_csv_allow_empty(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/F3_4C2C_A2_RUN_WITNESS_v1.json"),
    )
    args = parser.parse_args()
    run = args.run_dir.resolve()

    if not checksum_manifest_pass(run):
        raise SystemExit("RunBundle checksum verification failed")

    manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
    selected = json.loads(
        (run / "selected_component_artifact.json").read_text(encoding="utf-8")
    )
    primary = pd.read_csv(run / "primary_metrics.csv")
    grid = pd.read_csv(run / "grid_selection.csv")
    promotions = read_csv_allow_empty(run / "promotion_decisions.csv")
    bootstraps = read_csv_allow_empty(run / "bootstrap_intervals.csv")
    propagated = pd.read_csv(run / "propagated_guardrails.csv")

    witness = {
        "witness_id": "F3_4C2C_A2_RUN_WITNESS_V1",
        "source_phase": "F3.4c-2b",
        "source_attempt": "A2",
        "run_dir_basename": run.name,
        "run_status": manifest.get("status"),
        "implementation_commit": manifest.get("implementation_commit"),
        "component": manifest.get("component"),
        "proposed_selected_artifact_id": manifest.get(
            "proposed_selected_artifact_id"
        ),
        "candidate_selection_state": manifest.get("candidate_selection_state"),
        "candidate_artifacts": manifest.get("candidate_artifacts"),
        "eligible_family_winners": int(
            (
                grid["selected_within_family"]
                .astype(str)
                .str.lower()
                .eq("true")
            ).sum()
        ),
        "promotion_decision_rows": len(promotions),
        "bootstrap_rows": len(bootstraps),
        "propagated_guardrail_rows": len(propagated),
        "propagated_guardrails_pass": manifest.get("propagated_guardrails_pass"),
        "primary_reference_value": float(
            primary.loc[
                primary["artifact_id"]
                == "DG_TRIP_COUNT::COUNT_REF::REFERENCE",
                "value",
            ].iloc[0]
        ),
        "cal_rows": {
            "physical": manifest.get("cal_rows_read_total_physical"),
            "participation": manifest.get("cal_participation_rows"),
            "observed_tripday": manifest.get("cal_observed_tripday_rows"),
            "known_notrip": manifest.get("cal_known_notrip_rows"),
            "isolated": manifest.get("cal_isolated_evaluation_rows"),
            "count_target_observed_tripday": manifest.get(
                "cal_count_target_observed_tripday_rows"
            ),
            "count_target_unobserved_tripday": manifest.get(
                "cal_count_target_unobserved_tripday_rows"
            ),
            "count_guardrail_person_days": manifest.get(
                "cal_count_guardrail_person_days"
            ),
        },
        "boundaries": {
            "test_rows_read": manifest.get("test_rows_read"),
            "test_open_authorized": manifest.get("test_open_authorized"),
            "next_component_authorized": manifest.get("next_component_authorized"),
            "formal_g2": manifest.get("formal_g2"),
        },
        "selected_component_artifact_status": selected.get("status"),
        "selected_component_authorized_for_downstream": selected.get(
            "authorized_for_downstream"
        ),
        "file_sha256": {
            name: sha256(run / name)
            for name in WITNESS_FILES
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(witness, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(witness, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
