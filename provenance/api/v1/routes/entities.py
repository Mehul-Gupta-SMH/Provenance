"""Entity CRUD routes. No business logic here — everything delegates to entity_service."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from provenance.models.database import get_session
from provenance.models.entity import EntityCreate, EntityRead, EntityUpdate, entity_to_read
from provenance.services import entity_service

router = APIRouter(prefix="/entities", tags=["entities"])


@router.post("", response_model=EntityRead, status_code=201)
def create_entity(entity_in: EntityCreate, session: Session = Depends(get_session)) -> EntityRead:
    return entity_service.create_entity(entity_in, session)


@router.get("", response_model=List[EntityRead])
def list_entities(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    session: Session = Depends(get_session),
) -> List[EntityRead]:
    return entity_service.list_entities(session, skip=skip, limit=limit)


@router.get("/{entity_id}", response_model=EntityRead)
def get_entity(entity_id: int, session: Session = Depends(get_session)) -> EntityRead:
    entity = entity_service.get_entity(entity_id, session)
    if entity is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "ENTITY_NOT_FOUND", "detail": f"Entity {entity_id} not found"},
        )
    return entity_to_read(entity)


@router.patch("/{entity_id}", response_model=EntityRead)
def update_entity(
    entity_id: int,
    entity_in: EntityUpdate,
    session: Session = Depends(get_session),
) -> EntityRead:
    entity = entity_service.update_entity(entity_id, entity_in, session)
    if entity is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "ENTITY_NOT_FOUND", "detail": f"Entity {entity_id} not found"},
        )
    return entity_to_read(entity)


@router.delete("/{entity_id}")
def delete_entity(entity_id: int, session: Session = Depends(get_session)) -> dict:
    deleted = entity_service.delete_entity(entity_id, session)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"error": "ENTITY_NOT_FOUND", "detail": f"Entity {entity_id} not found"},
        )
    return {"deleted": True}
