"""Top-level /v1 API router, wrapping the aggregated resource routes."""

from fastapi import APIRouter

from provenance.api.v1.routes import router as v1_routes_router

router = APIRouter(prefix="/v1")
router.include_router(v1_routes_router)

__all__ = ["router"]
