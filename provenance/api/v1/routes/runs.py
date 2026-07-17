"""Run lifecycle routes: create (status=pending), get, list by entity.

No business logic here — everything delegates to run_service. Pipeline execution
(probes, collectors, divergence) is wired up via the PIPELINE HOOK block below.
"""

from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlmodel import Session, select

from provenance.config import Settings, get_settings
from provenance.core.divergence import DivergenceEngine, RunNotFoundError
from provenance.models.database import engine, get_session
from provenance.models.divergence_score import DivergenceScore
from provenance.models.run import Run, RunCreate, RunRead
from provenance.services import run_service
from provenance.services.run_service import EntityNotFoundError, ExperimentNotFoundError

router = APIRouter(prefix="/runs", tags=["runs"])


# --- PIPELINE HOOK (Phase 5) ---
def _run_pipeline(run_id: int, settings: Settings) -> None:
    """Adapter from the sync BackgroundTask to the async pipeline.

    Runs in FastAPI's background-task thread pool, so creating a fresh event loop
    and a Session isolated from the request Session is safe here (PLAN.md section 9,
    "Pipeline Call from Route").
    """
    import asyncio

    from provenance.core.pipeline import RunPipeline

    with Session(engine) as session:
        pipeline = RunPipeline(settings=settings, session=session)
        asyncio.run(pipeline.execute(run_id))
# --- END PIPELINE HOOK ---


@router.post("", response_model=RunRead, status_code=201)
def create_run(
    run_in: RunCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> Run:
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
    background_tasks.add_task(_run_pipeline, run.id, get_settings())
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


@router.post("/{run_id}/divergence", response_model=DivergenceScore)
def compute_divergence(run_id: int, session: Session = Depends(get_session)) -> DivergenceScore:
    try:
        return DivergenceEngine(session).compute_for_run(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "RUN_NOT_FOUND", "detail": str(exc)},
        ) from exc


@router.get("/{run_id}/divergence", response_model=DivergenceScore)
def get_divergence(run_id: int, session: Session = Depends(get_session)) -> DivergenceScore:
    score = session.exec(select(DivergenceScore).where(DivergenceScore.run_id == run_id)).first()
    if score is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "DIVERGENCE_NOT_FOUND",
                "detail": f"No divergence score for run {run_id}",
            },
        )
    return score
