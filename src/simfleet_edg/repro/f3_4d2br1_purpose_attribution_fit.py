from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd
import yaml

from simfleet_edg.evaluation.activity_chain_purpose_attribution import (
    backoff_selection_audit,
    fit_purpose_attribution,
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--artifact-output", type=Path, required=True)
    parser.add_argument("--witness-output", type=Path, required=True)
    args = parser.parse_args()

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    purpose = cfg["purpose_attribution"]
    source_cfg = purpose["train_input"]
    source = Path(source_cfg["path"])

    actual_sha = sha256(source)
    if actual_sha != source_cfg["sha256"]:
        raise SystemExit(f"TRAIN SHA mismatch: {actual_sha}")

    frame = pd.read_csv(source)
    if len(frame) != int(source_cfg["expected_rows"]):
        raise SystemExit(f"TRAIN row mismatch: {len(frame)}")

    artifact = fit_purpose_attribution(
        frame,
        source_n_min=int(purpose["return_previous"]["source_n_min"]),
    )
    artifact["source"] = {
        "path": str(source),
        "rows": len(frame),
        "sha256": actual_sha,
    }
    artifact["candidate_scope"] = (
        "SHARED_IDENTICAL_PRIMITIVE_FOR_ALL_SIX_ACTIVITY_CHAIN_CANDIDATES"
    )
    artifact["candidate_identity_in_rng_key"] = False
    artifact["calibration_rows_read"] = 0
    artifact["test_rows_read"] = 0

    args.artifact_output.parent.mkdir(parents=True, exist_ok=True)
    args.artifact_output.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    artifact_sha = sha256(args.artifact_output)

    total_weight = float(frame["fit_weight_W_GEW"].sum())
    rp_mask = frame["canonical_trip_purpose"].eq("RETURN_PREVIOUS")
    rp_weight = float(frame.loc[rp_mask, "fit_weight_W_GEW"].sum())
    eligible = frame[
        frame["target_destination_activity"]
        == frame["prefix_second_last_activity"]
    ]
    eligible_weight = float(eligible["fit_weight_W_GEW"].sum())
    audit = backoff_selection_audit(frame, artifact)

    witness = {
        "witness_id": "F3_4D2BR1_TRAIN_PURPOSE_WITNESS_V1",
        "phase": "F3.4d-2b-R1",
        "primitive_id": artifact["primitive_id"],
        "train_source_path": str(source),
        "train_source_sha256": actual_sha,
        "train_rows": len(frame),
        "return_previous_rows": int(rp_mask.sum()),
        "return_previous_weight_share": rp_weight / total_weight,
        "semantic_return_previous_violations": artifact[
            "semantic_validation"
        ]["return_previous_violations"],
        "semantic_direct_mapping_violations": artifact[
            "semantic_validation"
        ]["direct_mapping_violations"],
        "return_eligible_rows": len(eligible),
        "return_eligible_row_share": len(eligible) / len(frame),
        "return_eligible_weight_share": eligible_weight / total_weight,
        "global_weighted_p_return_previous": artifact[
            "global_return_eligible"
        ]["p_return_previous"],
        **audit,
        "purpose_artifact_sha256": artifact_sha,
        "calibration_rows_read": 0,
        "test_rows_read": 0,
        "candidate_selection": "NONE",
        "formal_g2": "NOT_EVALUATED",
    }
    args.witness_output.parent.mkdir(parents=True, exist_ok=True)
    args.witness_output.write_text(
        json.dumps(witness, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(witness, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
