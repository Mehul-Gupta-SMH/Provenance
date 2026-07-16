"""Aggregates all resource routers under a single APIRouter for /v1."""

from fastapi import APIRouter

from provenance.api.v1.routes import entities, experiments, runs

router = APIRouter()
router.include_router(entities.router)
router.include_router(experiments.router)
router.include_router(runs.router)

__all__ = ["router"]
