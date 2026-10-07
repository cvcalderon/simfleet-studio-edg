from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Final

GENERIC_PURPOSES: Final[tuple[str, ...]] = (
    "WORK_COMMUTE",
    "BUSINESS",
    "EDUCATION",
    "SHOPPING",
    "LEISURE",
    "OTHER",
)
FORBIDDEN_GENERIC_PURPOSES: Final[frozenset[str]] = frozenset({"RETURN_HOME", "ESCORT"})
INCLUDE_DECISIONS: Final[frozenset[str]] = frozenset(
    {"INCLUDE", "INCLUDE_AREA_FALLBACK", "INCLUDE_HOME_ANCHOR", "INCLUDE_HOME_FALLBACK_AREA"}
)
EXCLUDE_DECISIONS: Final[frozenset[str]] = frozenset({"EXCLUDE"})


@dataclass(frozen=True, slots=True)
class RegistryRule:
    rule_id: str
    priority: int
    rule_kind: str
    osm_key: str
    value_pattern: str
    geometry_scope: str
    supply_class: str
    eligible_purposes: tuple[str, ...]
    decision: str
    confidence: str
    evidence_basis: str
    notes: str

    @property
    def is_include(self) -> bool:
        return self.decision in INCLUDE_DECISIONS

    @property
    def is_exclude(self) -> bool:
        return self.decision in EXCLUDE_DECISIONS

    @property
    def is_area_fallback(self) -> bool:
        return self.decision == "INCLUDE_AREA_FALLBACK" or self.supply_class.endswith(
            "_AREA_FALLBACK"
        )

    @property
    def is_residential(self) -> bool:
        return self.decision in {"INCLUDE_HOME_ANCHOR", "INCLUDE_HOME_FALLBACK_AREA"}


@dataclass(frozen=True, slots=True)
class RegistryDecision:
    admitted: bool
    excluded: bool
    unmapped_default_deny: bool
    matched_rule_ids: tuple[str, ...]
    include_rule_ids: tuple[str, ...]
    exclusion_rule_ids: tuple[str, ...]
    eligible_purposes: tuple[str, ...]
    supply_classes: tuple[str, ...]
    primary_supply_class: str | None
    residential_support: bool
    area_fallback: bool


class EligibilityRegistry:
    def __init__(self, rules: tuple[RegistryRule, ...]) -> None:
        if not rules:
            raise ValueError("A3 registry is empty")
        self.rules = tuple(sorted(rules, key=lambda rule: (-rule.priority, rule.rule_id)))
        self._validate()

    @classmethod
    def from_csv(cls, path: Path) -> EligibilityRegistry:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {
                "rule_id",
                "priority",
                "rule_kind",
                "osm_key",
                "value_pattern",
                "geometry_scope",
                "supply_class",
                "eligible_purposes",
                "decision",
                "confidence",
                "evidence_basis",
                "notes",
            }
            if reader.fieldnames is None or set(reader.fieldnames) != required:
                raise ValueError("Unexpected A3 registry columns")
            rows = tuple(_rule_from_row(row) for row in reader)
        return cls(rows)

    def _validate(self) -> None:
        ids = [rule.rule_id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("A3 registry contains duplicate rule_id values")
        guards = {
            purpose
            for rule in self.rules
            if rule.rule_kind == "PURPOSE_GUARD"
            for purpose in rule.eligible_purposes
        }
        if not FORBIDDEN_GENERIC_PURPOSES.issubset(guards):
            raise ValueError("A3 registry is missing HOME/ESCORT generic-supply guards")
        for rule in self.rules:
            if rule.is_include and FORBIDDEN_GENERIC_PURPOSES.intersection(
                rule.eligible_purposes
            ):
                raise ValueError(f"Forbidden generic purpose in include rule {rule.rule_id}")
            if rule.is_include:
                unknown = set(rule.eligible_purposes).difference(GENERIC_PURPOSES)
                if unknown:
                    raise ValueError(
                        f"Unknown generic purpose(s) in {rule.rule_id}: {sorted(unknown)}"
                    )
        defaults = [rule for rule in self.rules if rule.rule_kind == "DEFAULT_DENY"]
        if len(defaults) != 1 or defaults[0].decision != "EXCLUDE_UNMAPPED":
            raise ValueError("A3 registry must contain exactly one default-deny rule")

    def evaluate(self, tags: dict[str, str], geometry_kind: str) -> RegistryDecision:
        candidate_rules = tuple(
            rule
            for rule in self.rules
            if rule.rule_kind not in {"PURPOSE_GUARD", "DEFAULT_DENY"}
            and _rule_matches(rule, tags, geometry_kind)
        )
        include_rules = tuple(rule for rule in candidate_rules if rule.is_include)
        exclusion_rules = tuple(rule for rule in candidate_rules if rule.is_exclude)

        highest_include = max((rule.priority for rule in include_rules), default=-1)
        overriding_exclusions = tuple(
            rule for rule in exclusion_rules if rule.priority > highest_include
        )
        if overriding_exclusions:
            return RegistryDecision(
                admitted=False,
                excluded=True,
                unmapped_default_deny=False,
                matched_rule_ids=tuple(rule.rule_id for rule in candidate_rules),
                include_rule_ids=tuple(rule.rule_id for rule in include_rules),
                exclusion_rule_ids=tuple(rule.rule_id for rule in overriding_exclusions),
                eligible_purposes=(),
                supply_classes=(),
                primary_supply_class=None,
                residential_support=False,
                area_fallback=False,
            )

        if not include_rules:
            return RegistryDecision(
                admitted=False,
                excluded=False,
                unmapped_default_deny=True,
                matched_rule_ids=(),
                include_rule_ids=(),
                exclusion_rule_ids=(),
                eligible_purposes=(),
                supply_classes=(),
                primary_supply_class=None,
                residential_support=False,
                area_fallback=False,
            )

        purposes = tuple(
            purpose
            for purpose in GENERIC_PURPOSES
            if any(purpose in rule.eligible_purposes for rule in include_rules)
        )
        supply_classes = tuple(
            dict.fromkeys(
                rule.supply_class for rule in include_rules if rule.supply_class != "NONE"
            )
        )
        primary = supply_classes[0] if supply_classes else None
        residential = any(rule.is_residential for rule in include_rules)
        admitted = bool(purposes) or residential
        return RegistryDecision(
            admitted=admitted,
            excluded=False,
            unmapped_default_deny=False,
            matched_rule_ids=tuple(rule.rule_id for rule in candidate_rules),
            include_rule_ids=tuple(rule.rule_id for rule in include_rules),
            exclusion_rule_ids=(),
            eligible_purposes=purposes,
            supply_classes=supply_classes,
            primary_supply_class=primary,
            residential_support=residential,
            area_fallback=bool(include_rules) and all(rule.is_area_fallback for rule in include_rules),
        )


def _rule_from_row(row: dict[str, str]) -> RegistryRule:
    return RegistryRule(
        rule_id=row["rule_id"].strip(),
        priority=int(row["priority"]),
        rule_kind=row["rule_kind"].strip(),
        osm_key=row["osm_key"].strip(),
        value_pattern=row["value_pattern"].strip(),
        geometry_scope=row["geometry_scope"].strip(),
        supply_class=row["supply_class"].strip(),
        eligible_purposes=tuple(
            purpose.strip()
            for purpose in row["eligible_purposes"].split(";")
            if purpose.strip()
        ),
        decision=row["decision"].strip(),
        confidence=row["confidence"].strip(),
        evidence_basis=row["evidence_basis"].strip(),
        notes=row["notes"].strip(),
    )


def _geometry_matches(scope: str, geometry_kind: str) -> bool:
    if scope == "ANY":
        return True
    if scope == "POINT_OR_POLYGON":
        return geometry_kind in {"POINT", "POLYGON"}
    return scope == geometry_kind


def _rule_matches(rule: RegistryRule, tags: dict[str, str], geometry_kind: str) -> bool:
    if not _geometry_matches(rule.geometry_scope, geometry_kind):
        return False

    if rule.rule_kind == "LIFECYCLE_KEY_PREFIX":
        prefixes = tuple(
            token.removesuffix("*")
            for token in rule.osm_key.split("|")
            if token.endswith("*")
        )
        return any(key.startswith(prefix) for key in tags for prefix in prefixes)

    if rule.rule_kind == "INACTIVE_VALUE":
        inactive = set(rule.value_pattern.split("|"))
        return any(value in inactive for value in tags.values())

    if rule.osm_key not in tags:
        return False
    value = tags[rule.osm_key]

    if rule.rule_kind in {"EXACT", "TRANSPORT_DESTINATION_GUARD"}:
        accepted = set(rule.value_pattern.split("|"))
        return value in accepted
    if rule.rule_kind == "VALUE_SET":
        return value in set(rule.value_pattern.split("|"))
    if rule.rule_kind == "WILDCARD_ACTIVE":
        return bool(value) and value != "*"
    raise ValueError(f"Unsupported A3 rule kind: {rule.rule_kind}")
