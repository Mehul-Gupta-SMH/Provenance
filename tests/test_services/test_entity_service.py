"""Tests for provenance/services/entity_service.py (PLAN.md section 14, Services)."""
from __future__ import annotations

import time

from provenance.models.entity import EntityCreate, EntityUpdate
from provenance.services import entity_service


def test_create_entity_json_list_round_trip(session):
    entity_in = EntityCreate(
        name="Acme",
        category="graph database",
        competitors=["Rival", "Other"],
        query_seeds=["best graph db", "graph db comparison"],
    )

    read = entity_service.create_entity(entity_in, session)

    assert read.id is not None
    assert read.competitors == ["Rival", "Other"]
    assert read.query_seeds == ["best graph db", "graph db comparison"]


def test_get_and_list_entities(session):
    entity_service.create_entity(EntityCreate(name="Acme", category="graph database"), session)
    entity_service.create_entity(EntityCreate(name="Other", category="graph database"), session)

    all_entities = entity_service.list_entities(session)
    assert len(all_entities) == 2

    limited = entity_service.list_entities(session, skip=0, limit=1)
    assert len(limited) == 1

    fetched = entity_service.get_entity(all_entities[0].id, session)
    assert fetched is not None
    assert fetched.name == all_entities[0].name


def test_get_entity_missing_returns_none(session):
    assert entity_service.get_entity(999999, session) is None


def test_update_entity_round_trips_json_lists_and_bumps_updated_at(session):
    read = entity_service.create_entity(
        EntityCreate(name="Acme", category="graph database", competitors=["Rival"]), session
    )
    original_updated_at = read.updated_at

    time.sleep(0.001)  # ensure datetime.utcnow() strictly advances
    updated = entity_service.update_entity(
        read.id,
        EntityUpdate(competitors=["Rival", "NewCo"], category="vector database"),
        session,
    )

    assert updated is not None
    assert updated.category == "vector database"
    assert updated.competitors_json == '["Rival", "NewCo"]'
    assert updated.updated_at > original_updated_at


def test_update_entity_missing_returns_none(session):
    result = entity_service.update_entity(999999, EntityUpdate(category="x"), session)
    assert result is None


def test_delete_entity(session):
    read = entity_service.create_entity(
        EntityCreate(name="Acme", category="graph database"), session
    )

    assert entity_service.delete_entity(read.id, session) is True
    assert entity_service.get_entity(read.id, session) is None
    assert entity_service.delete_entity(read.id, session) is False
