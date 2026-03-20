from sqlmodel import SQLModel, Field
from typing import Optional, List
from datetime import datetime
import json


class EntityBase(SQLModel):
    name: str = Field(index=True)
    category: str
    url: Optional[str] = None
    # Lists stored as JSON strings; service layer serializes/deserializes
    competitors_json: str = Field(default="[]")
    query_seeds_json: str = Field(default="[]")


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


class EntityRead(SQLModel):
    id: int
    name: str
    category: str
    url: Optional[str]
    competitors: List[str]
    query_seeds: List[str]
    created_at: datetime
    updated_at: datetime


class EntityUpdate(SQLModel):
    name: Optional[str] = None
    category: Optional[str] = None
    url: Optional[str] = None
    competitors: Optional[List[str]] = None
    query_seeds: Optional[List[str]] = None


def entity_to_read(entity: Entity) -> EntityRead:
    return EntityRead(
        id=entity.id,
        name=entity.name,
        category=entity.category,
        url=entity.url,
        competitors=json.loads(entity.competitors_json),
        query_seeds=json.loads(entity.query_seeds_json),
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )
