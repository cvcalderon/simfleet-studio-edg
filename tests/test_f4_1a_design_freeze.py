import csv
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def cfg():
    return yaml.safe_load(
        (
            ROOT
            / "configs/f4/f4_1a_m3_design_freeze_v1.yaml"
        ).read_text(encoding="utf-8")
    )


def test_upstream_closed():
    c = cfg()

    assert (
        c["required_parent_commit"]
        == "877e718a8c3fe088158eafa6332bdfb466a81213"
    )

    assert c["upstream"]["g1"] == "PASS_CLOSED"

    assert (
        c["upstream"]["g2"]
        == "PASS_CLOSED_DO_NOT_REOPEN"
    )

    assert (
        c["upstream"]["mid_test"]
        == "CONSUMED_BY_G2_DO_NOT_REOPEN"
    )


def test_population_binding():
    p = cfg()["upstream"]["accepted_population"]

    assert (
        p["candidate_id"]
        == "P_CONSTR_RMIN_V2_HD_U"
    )

    assert p["scale_id"] == "M"
    assert p["persons"] == 100000
    assert p["households"] == 54828
    assert p["home_zone_level"] == "BEZIRK"
    assert p["home_zone_count"] == 12


def test_dgen_consume_only():
    c = cfg()

    assert c["upstream"]["dgen_selected_pipeline"] == [
        "PA1",
        "COUNT_REF",
        "CHA2",
        "TIME_B_TB2",
        "DIST_REF_REFERENCE",
    ]

    assert (
        c["upstream"]["dgen_policy"]
        == "FROZEN_CONSUME_ONLY_NO_REFIT_NO_CAL_NO_TEST"
    )


def test_m3_blindness():
    s = cfg()["m3_scope"]

    assert s["mode_blind"] is True
    assert s["route_blind"] is True
    assert s["execution_blind"] is True


def test_home_semantics():
    h = cfg()["contracts"]["home"]

    assert h["source_resolution"] == "BEZIRK_ONLY"

    assert (
        h["interpretation"]
        == "spatial_context_not_point_location"
    )

    assert h["finer_realization_required"] is True

    assert (
        h["exact_mid_home_coordinate_available"]
        is False
    )


def test_distance_semantics():
    d = cfg()["contracts"]["distance"]

    assert (
        d["upstream_artifact"]
        == "DIST_REF_REFERENCE"
    )

    assert d["not_exact_od"] is True
    assert d["not_route_length"] is True
    assert d["not_mode_specific"] is True


def test_candidates_unselected():
    path = (
        ROOT
        / "docs/F4_1A_SPATIAL_CANDIDATE_MATRIX_v1.csv"
    )

    with path.open(
        encoding="utf-8",
        newline="",
    ) as fh:
        rows = list(csv.DictReader(fh))

    assert [
        row["candidate_id"]
        for row in rows
    ] == [
        "S_NEAR",
        "S_DIST",
        "S_ATTR",
    ]

    assert all(
        row["selection_status"]
        == "NOT_YET_AUTHORIZED"
        for row in rows
    )


def test_roles_forbid_test_and_future():
    path = (
        ROOT
        / "docs/"
        "F4_1A_SPATIAL_EVIDENCE_ROLE_REGISTRY_v1.csv"
    )

    with path.open(
        encoding="utf-8",
        newline="",
    ) as fh:
        rows = {
            row["evidence_id"]: row
            for row in csv.DictReader(fh)
        }

    assert (
        rows["MID-TEST"]["role"]
        == "FORBIDDEN_CONSUMED"
    )

    assert (
        rows["M5-MODE"]["role"]
        == "FORBIDDEN_FUTURE_INFORMATION"
    )

    assert (
        rows["M4-ROUTE"]["role"]
        == "FORBIDDEN_FUTURE_INFORMATION"
    )

    assert (
        rows["M6-EXECUTION"]["role"]
        == "FORBIDDEN_FUTURE_INFORMATION"
    )


def test_topology_not_overclaimed():
    assert (
        cfg()["spatial_evidence"]["lor_2021"][
            "topology_validation"
        ]
        == "DEFERRED_TO_F4_1B_ENVIRONMENT_GATE"
    )


def test_entry_decision():
    path = (
        ROOT
        / "docs/F4_1A_ENTRY_AUDIT_DECISION_v1.json"
    )

    d = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    assert (
        d["decision"]["case_a_home_already_fine"]
        == "REJECT"
    )

    assert (
        d["decision"][
            "residential_refinement_required"
        ]
        is True
    )

    assert (
        d["decision"][
            "spatial_supply_contract_required"
        ]
        is True
    )

    assert (
        d["decision"][
            "candidate_selection_authorized"
        ]
        is False
    )
