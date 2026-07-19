"""Service layer for Entity CRUD. Routes call these functions only — no logic in routes."""

import json
from datetime import datetime
from typing import List, Optional

from sqlmodel import Session, select

from provenance.models.entity import Entity, EntityCreate, EntityRead, EntityUpdate, entity_to_read


def create_entity(entity_in: EntityCreate, session: Session) -> EntityRead:
    entity = Entity(
        name=entity_in.name,
        category=entity_in.category,
        url=entity_in.url,
        competitors_json=json.dumps(entity_in.competitors),
        query_seeds_json=json.dumps(entity_in.query_seeds),
        aliases_json=json.dumps(entity_in.aliases),
    )
    session.add(entity)
    session.commit()
    session.refresh(entity)
    return entity_to_read(entity)


def get_entity(entity_id: int, session: Session) -> Optional[Entity]:
    return session.get(Entity, entity_id)


def list_entities(session: Session, skip: int = 0, limit: int = 100) -> List[EntityRead]:
    entities = session.exec(select(Entity).offset(skip).limit(limit)).all()
    return [entity_to_read(e) for e in entities]


def update_entity(entity_id: int, entity_in: EntityUpdate, session: Session) -> Optional[Entity]:
    entity = session.get(Entity, entity_id)
    if entity is None:
        return None

    update_data = entity_in.model_dump(exclude_unset=True)

    if "name" in update_data:
        entity.name = update_data["name"]
    if "category" in update_data:
        entity.category = update_data["category"]
    if "url" in update_data:
        entity.url = update_data["url"]
    if "competitors" in update_data and update_data["competitors"] is not None:
        entity.competitors_json = json.dumps(update_data["competitors"])
    if "query_seeds" in update_data and update_data["query_seeds"] is not None:
        entity.query_seeds_json = json.dumps(update_data["query_seeds"])
    if "aliases" in update_data and update_data["aliases"] is not None:
        entity.aliases_json = json.dumps(update_data["aliases"])

    entity.updated_at = datetime.utcnow()

    session.add(entity)
    session.commit()
    session.refresh(entity)
    return entity


def delete_entity(entity_id: int, session: Session) -> bool:
    entity = session.get(Entity, entity_id)
    if entity is None:
        return False
    session.delete(entity)
    session.commit()
    return True
