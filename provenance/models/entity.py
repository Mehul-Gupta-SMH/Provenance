import json
from datetime import datetime
from typing import List, Optional

from sqlmodel import Field, SQLModel


class EntityBase(SQLModel):
    name: str = Field(index=True)
    category: str
    url: Optional[str] = None
    # Lists stored as JSON strings; service layer serializes/deserializes
    competitors_json: str = Field(default="[]")
    query_seeds_json: str = Field(default="[]")
    aliases_json: str = Field(default="[]")


class Entity(EntityBase, table=True):
    __tablename__ = "entity"
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class EntityCreate(SQLModel):
    name: str
    category: str
    url: Optional[str] = None
    competitors: List[str] = []
    query_seeds: List[str] = []
    aliases: List[str] = []


class EntityRead(SQLModel):
    id: int
    name: str
    category: str
    url: Optional[str]
    competitors: List[str]
    query_seeds: List[str]
    aliases: List[str]
    created_at: datetime
    updated_at: datetime


class EntityUpdate(SQLModel):
    name: Optional[str] = None
    category: Optional[str] = None
    url: Optional[str] = None
    competitors: Optional[List[str]] = None
    query_seeds: Optional[List[str]] = None
    aliases: Optional[List[str]] = None


def entity_to_read(entity: Entity) -> EntityRead:
    return EntityRead(
        id=entity.id,
        name=entity.name,
        category=entity.category,
        url=entity.url,
        competitors=json.loads(entity.competitors_json),
        query_seeds=json.loads(entity.query_seeds_json),
        aliases=json.loads(entity.aliases_json),
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def entity_name_variants(entity: Entity) -> set[str]:
    """Lowercased {entity.name} ∪ aliases_json, for alias-aware name matching.

    Tolerates empty/malformed aliases_json (falls back to just {name})."""
    variants = {entity.name.strip().lower()}
    try:
        aliases = json.loads(entity.aliases_json)
    except (TypeError, ValueError):
        return variants
    if not isinstance(aliases, list):
        return variants
    variants.update(alias.strip().lower() for alias in aliases if isinstance(alias, str))
    return variants


def matches_entity(candidate_name: str, entity: Entity) -> bool:
    """True if candidate_name matches the entity's canonical name or any alias."""
    return candidate_name.strip().lower() in entity_name_variants(entity)
