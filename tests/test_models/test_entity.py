"""Tests for provenance/models/entity.py."""
from __future__ import annotations

from provenance.models.entity import (
    Entity,
    entity_name_variants,
    entity_to_read,
    matches_entity,
)


def test_entity_defaults_to_empty_json_lists():
    entity = Entity(name="Acme", category="graph database")

    assert entity.competitors_json == "[]"
    assert entity.query_seeds_json == "[]"
    assert entity.aliases_json == "[]"


def test_entity_to_read_deserializes_json_lists():
    entity = Entity(
        id=1,
        name="Acme",
        category="graph database",
        competitors_json='["Rival", "Other"]',
        query_seeds_json='["best graph db"]',
        aliases_json='["Acme Inc", "AcmeDB"]',
    )

    read = entity_to_read(entity)

    assert read.competitors == ["Rival", "Other"]
    assert read.query_seeds == ["best graph db"]
    assert read.aliases == ["Acme Inc", "AcmeDB"]
    assert read.name == "Acme"


def test_entity_name_variants_includes_name_and_aliases_case_insensitively():
    entity = Entity(
        name="Neo4j",
        category="graph database",
        aliases_json='["neo4j", "Neo 4j"]',
    )

    assert entity_name_variants(entity) == {"neo4j", "neo 4j"}


def test_entity_name_variants_tolerates_empty_and_malformed_aliases_json():
    empty = Entity(name="Acme", category="graph database", aliases_json="[]")
    malformed = Entity(name="Acme", category="graph database", aliases_json="not json")
    wrong_type = Entity(name="Acme", category="graph database", aliases_json='{"a": 1}')

    assert entity_name_variants(empty) == {"acme"}
    assert entity_name_variants(malformed) == {"acme"}
    assert entity_name_variants(wrong_type) == {"acme"}


def test_matches_entity_is_case_insensitive_and_checks_aliases():
    entity = Entity(
        name="Neo4j",
        category="graph database",
        aliases_json='["Neo 4j"]',
    )

    assert matches_entity("NEO4J", entity) is True
    assert matches_entity(" neo 4j ", entity) is True
    assert matches_entity("Other", entity) is False
