from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd
import yaml

from simfleet_edg.demand.training_data import DATASETS, PARTITIONS, source_hash_validation

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/f3/f3_2b_materialize_training_data.yaml"


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def main() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    contract = config["contract"]
    source_manifest = ROOT / str(contract["source_manifest"])
    sources = source_hash_validation(ROOT, source_manifest)
    schema = pd.read_csv(ROOT / str(contract["dataset_schema"]))
    counts = pd.read_csv(ROOT / str(contract["expected_counts"]))
    f32a = yaml.safe_load((ROOT / str(contract["materialization"])).read_text(encoding="utf-8"))

    checks = {
        "config_present": CONFIG.is_file(),
        "head_is_f3_2a_freeze": git("rev-parse", "HEAD") == config["required_design_parent_commit"],
        "parent_contract_exact": f32a["required_parent_commit"]
        == "58bb4183a9557b8b8b069552813db9530cb848b0",
        "partitions_exact": tuple(config["partitions"]) == PARTITIONS,
        "test_forbidden": config["forbidden_partitions"] == ["TEST"],
        "output_absent": not (ROOT / str(config["output_root"])).exists(),
        "sources_13": len(sources) == 13,
        "source_hashes_exact": sources["status"].eq("PASS").all(),
        "datasets_8": set(schema["dataset"]) == set(DATASETS),
        "count_rows_16": len(counts) == 16,
        "counts_train_cal_only": set(counts["partition"]) == set(PARTITIONS),
        "schema_has_no_km_routing": not schema["column"].str.contains("km_routing", case=False).any(),
        "schema_has_no_mode": not schema["column"].str.contains("mode", case=False).any(),
        "r4_not_consumed": (
            pd.read_csv(source_manifest)
            .loc[lambda x: x["source_id"].str.startswith("r4_"), "consumed_for_rows"]
            .eq("NO")
            .all()
        ),
        "f0_3g_witness_present": (
            ROOT
            / "configs/reproduction/reference/simfleet_edg_F0_3g_demand_variable_role_registry_v1.csv"
        ).is_file(),
        "no_models_emitted_by_contract": "model_parameters" in f32a["forbidden_outputs"],
    }
    # Pandas reductions may return numpy.bool_, which is truthy but is not
    # accepted by the stdlib JSON encoder.  Normalize the verification
    # boundary to built-in bool without changing any check semantics.
    checks = {name: bool(value) for name, value in checks.items()}
    status = "PASS" if all(checks.values()) else "FAIL"
    print(
        json.dumps(
            {
                "status": status,
                "checks": checks,
                "counts": {
                    "sources": len(sources),
                    "datasets": len(set(schema["dataset"])),
                    "expected_count_rows": len(counts),
                },
            },
            indent=2,
        )
    )
    if status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
