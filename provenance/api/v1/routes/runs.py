"""Run lifecycle routes: create (status=pending), get, list by entity.

No business logic here — everything delegates to run_service. Pipeline execution
(probes, collectors, divergence) is NOT wired up yet; see the hook comment below.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from provenance.models.database import get_session
from provenance.models.run import Run, RunCreate, RunRead
from provenance.services import run_service
from provenance.services.run_service import EntityNotFoundError, ExperimentNotFoundError

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunRead, status_code=201)
def create_run(run_in: RunCreate, session: Session = Depends(get_session)) -> Run:
    try:
        run = run_service.create_run(run_in, session)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "ENTITY_NOT_FOUND", "detail": str(exc)},
        ) from exc
    except ExperimentNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "EXPERIMENT_NOT_FOUND", "detail": str(exc)},
        ) from exc

    # --- PIPELINE HOOK (Phase 5) ---
    # A later phase will fire the background pipeline here, e.g.:
    #   background_tasks.add_task(_run_pipeline, run.id, settings)
    # core/pipeline.py does not exist yet — do not import it. Run stays `pending`
    # until the pipeline phase wires up the status transitions.
    # --- END PIPELINE HOOK ---

    return run


@router.get("/{run_id}", response_model=RunRead)
def get_run(run_id: int, session: Session = Depends(get_session)) -> Run:
    run = run_service.get_run(run_id, session)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "RUN_NOT_FOUND", "detail": f"Run {run_id} not found"},
        )
    return run


@router.get("", response_model=List[RunRead])
def list_runs(
    entity_id: Optional[int] = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    session: Session = Depends(get_session),
) -> List[Run]:
    return run_service.list_runs(session, entity_id=entity_id, skip=skip, limit=limit)
