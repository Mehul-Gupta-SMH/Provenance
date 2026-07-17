"""Analysis routes: competitor delta and gap analysis (PLAN.md section 12).

No business logic here — everything delegates to core/analysis.py. Handlers
translate FingerprintBuilder's domain exceptions into structured 404s per the
error standard in PLAN.md section 12 ({"error": ..., "detail": ...}).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from provenance.core.analysis import (
    CompetitorDelta,
    CompetitorDeltaResult,
    EntityFingerprint,
    EntityNotFoundError,
    FingerprintBuilder,
    GapAnalyzer,
    GapItem,
    NoCompletedRunError,
)
from provenance.models.database import get_session

router = APIRouter(prefix="/analysis", tags=["analysis"])


class CompetitorDeltaRequest(BaseModel):
    entity_id: int
    competitor_entity_id: int
    entity_run_id: Optional[int] = None  # defaults to latest completed run
    competitor_run_id: Optional[int] = None  # defaults to latest completed run


class GapAnalysisRequest(BaseModel):
    entity_id: int
    competitor_entity_id: int
    entity_run_id: Optional[int] = None
    competitor_run_id: Optional[int] = None


def _build_fingerprint_or_404(
    builder: FingerprintBuilder, entity_id: int, run_id: Optional[int]
) -> EntityFingerprint:
    try:
        return builder.build(entity_id, run_id)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "ENTITY_NOT_FOUND", "detail": str(exc)},
        ) from exc
    except NoCompletedRunError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "RUN_NOT_COMPLETED", "detail": str(exc)},
        ) from exc


@router.post("/competitor-delta", response_model=CompetitorDeltaResult)
def competitor_delta(
    req: CompetitorDeltaRequest, session: Session = Depends(get_session)
) -> CompetitorDeltaResult:
    builder = FingerprintBuilder(session)
    entity_fp = _build_fingerprint_or_404(builder, req.entity_id, req.entity_run_id)
    competitor_fp = _build_fingerprint_or_404(
        builder, req.competitor_entity_id, req.competitor_run_id
    )
    return CompetitorDelta().compute(entity_fp, competitor_fp)


@router.post("/gap", response_model=List[GapItem])
def gap_analysis(
    req: GapAnalysisRequest, session: Session = Depends(get_session)
) -> List[GapItem]:
    builder = FingerprintBuilder(session)
    entity_fp = _build_fingerprint_or_404(builder, req.entity_id, req.entity_run_id)
    competitor_fp = _build_fingerprint_or_404(
        builder, req.competitor_entity_id, req.competitor_run_id
    )
    delta_result = CompetitorDelta().compute(entity_fp, competitor_fp)
    return GapAnalyzer().analyze(delta_result)
