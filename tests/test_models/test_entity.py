"""Tests for provenance/models/entity.py."""
from __future__ import annotations

from provenance.models.entity import Entity, entity_to_read


def test_entity_defaults_to_empty_json_lists():
    entity = Entity(name="Acme", category="graph database")

    assert entity.competitors_json == "[]"
    assert entity.query_seeds_json == "[]"


def test_entity_to_read_deserializes_json_lists():
    entity = Entity(
        id=1,
        name="Acme",
        category="graph database",
        competitors_json='["Rival", "Other"]',
        query_seeds_json='["best graph db"]',
    )

    read = entity_to_read(entity)

    assert read.competitors == ["Rival", "Other"]
    assert read.query_seeds == ["best graph db"]
    assert read.name == "Acme"
