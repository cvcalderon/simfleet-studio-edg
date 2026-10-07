from pathlib import Path

from simfleet_edg.spatial.osm_registry import (
    FORBIDDEN_GENERIC_PURPOSES,
    EligibilityRegistry,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs/F4_1C_A3_OSM_TAG_TO_PURPOSE_ELIGIBILITY_REGISTRY_v1.csv"


def _registry() -> EligibilityRegistry:
    return EligibilityRegistry.from_csv(REGISTRY)


def test_lifecycle_exclusion_overrides_include() -> None:
    decision = _registry().evaluate(
        {"shop": "supermarket", "disused:amenity": "restaurant"}, "POINT"
    )
    assert decision.excluded is True
    assert decision.admitted is False
    assert "A3-EXC-001" in decision.exclusion_rule_ids


def test_generic_building_and_vacant_shop_are_excluded() -> None:
    registry = _registry()
    assert registry.evaluate({"building": "yes"}, "POLYGON").excluded is True
    assert registry.evaluate({"shop": "vacant"}, "POINT").excluded is True


def test_unknown_tag_is_closed_world_default_deny() -> None:
    decision = _registry().evaluate({"amenity": "future_unmapped_value"}, "POINT")
    assert decision.admitted is False
    assert decision.unmapped_default_deny is True


def test_multiple_tags_union_purposes_in_deterministic_order() -> None:
    decision = _registry().evaluate({"amenity": "bank", "shop": "clothes"}, "POINT")
    assert decision.admitted is True
    assert decision.eligible_purposes == ("WORK_COMMUTE", "BUSINESS", "SHOPPING", "OTHER")


def test_home_and_escort_never_enter_generic_supply() -> None:
    registry = _registry()
    for rule in registry.rules:
        if rule.is_include:
            assert not FORBIDDEN_GENERIC_PURPOSES.intersection(rule.eligible_purposes)
    residential = registry.evaluate({"building": "apartments"}, "POLYGON")
    assert residential.residential_support is True
    assert residential.eligible_purposes == ()


def test_transport_facility_is_excluded() -> None:
    decision = _registry().evaluate({"amenity": "parking"}, "POINT")
    assert decision.excluded is True
    assert decision.admitted is False


def test_recycling_maps_other_and_work_not_business() -> None:
    decision = _registry().evaluate({"amenity": "recycling"}, "POINT")
    assert decision.eligible_purposes == ("WORK_COMMUTE", "OTHER")
    assert "BUSINESS" not in decision.eligible_purposes


def test_explicit_facility_precedes_area_fallback() -> None:
    decision = _registry().evaluate(
        {"building": "commercial", "landuse": "commercial"}, "POLYGON"
    )
    assert decision.primary_supply_class == "FACILITY"
    assert decision.area_fallback is False
