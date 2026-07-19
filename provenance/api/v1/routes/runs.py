"""Run lifecycle routes: create (status=pending), get, list by entity.

No business logic here — everything delegates to run_service. Pipeline execution
(probes, collectors, divergence) is wired up via the PIPELINE HOOK block below.
"""

from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlmodel import Session, select

from provenance.config import Settings, get_settings
from provenance.core.action_report import ActionReport, ActionReportBuilder
from provenance.core.action_report import RunNotFoundError as ActionReportRunNotFoundError
from provenance.core.citation_analytics import CitationAnalytics, CitationAnalyticsEngine
from provenance.core.divergence import DivergenceEngine
from provenance.core.divergence import RunNotFoundError as DivergenceRunNotFoundError
from provenance.models.citation import CitationRead
from provenance.models.data_point import DataPointRead
from provenance.models.database import engine, get_session
from provenance.models.demand_signal import DemandSignalRead
from provenance.models.divergence_score import DivergenceScore
from provenance.models.llm_signal import LLMSignalRead
from provenance.models.query_probe import QueryProbeRead
from provenance.models.run import RunCreate, RunRead, run_to_read
from provenance.services import run_service, signal_service
from provenance.services.run_service import EntityNotFoundError, ExperimentNotFoundError
from provenance.services.signal_service import RunNotFoundError as SignalRunNotFoundError

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
) -> RunRead:
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

    return run_to_read(run)


@router.get("/{run_id}", response_model=RunRead)
def get_run(run_id: int, session: Session = Depends(get_session)) -> RunRead:
    run = run_service.get_run(run_id, session)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "RUN_NOT_FOUND", "detail": f"Run {run_id} not found"},
        )
    return run_to_read(run)


@router.get("", response_model=List[RunRead])
def list_runs(
    entity_id: Optional[int] = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    session: Session = Depends(get_session),
) -> List[RunRead]:
    runs = run_service.list_runs(session, entity_id=entity_id, skip=skip, limit=limit)
    return [run_to_read(r) for r in runs]


@router.post("/{run_id}/divergence", response_model=DivergenceScore)
def compute_divergence(run_id: int, session: Session = Depends(get_session)) -> DivergenceScore:
    try:
        return DivergenceEngine(session).compute_for_run(run_id)
    except DivergenceRunNotFoundError as exc:
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


@router.get("/{run_id}/probes", response_model=List[QueryProbeRead])
def list_probes(run_id: int, session: Session = Depends(get_session)) -> List[QueryProbeRead]:
    try:
        return signal_service.list_probes_for_run(run_id, session)
    except SignalRunNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "RUN_NOT_FOUND", "detail": str(exc)},
        ) from exc


@router.get("/{run_id}/signals", response_model=List[LLMSignalRead])
def list_signals(run_id: int, session: Session = Depends(get_session)) -> List[LLMSignalRead]:
    try:
        return signal_service.list_signals_for_run(run_id, session)
    except SignalRunNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "RUN_NOT_FOUND", "detail": str(exc)},
        ) from exc


@router.get("/{run_id}/citations", response_model=List[CitationRead])
def list_citations(run_id: int, session: Session = Depends(get_session)) -> List[CitationRead]:
    try:
        return signal_service.list_citations_for_run(run_id, session)
    except SignalRunNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "RUN_NOT_FOUND", "detail": str(exc)},
        ) from exc


@router.get("/{run_id}/citation-analytics", response_model=CitationAnalytics)
def get_citation_analytics(
    run_id: int, session: Session = Depends(get_session)
) -> CitationAnalytics:
    try:
        return CitationAnalyticsEngine(session).for_run(run_id)
    except SignalRunNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "RUN_NOT_FOUND", "detail": str(exc)},
        ) from exc


@router.get("/{run_id}/demand", response_model=List[DemandSignalRead])
def list_demand(run_id: int, session: Session = Depends(get_session)) -> List[DemandSignalRead]:
    try:
        return signal_service.list_demand_for_run(run_id, session)
    except SignalRunNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "RUN_NOT_FOUND", "detail": str(exc)},
        ) from exc


@router.get("/{run_id}/datapoints", response_model=List[DataPointRead])
def list_datapoints(
    run_id: int,
    signal_family: Optional[str] = Query(default=None),
    session: Session = Depends(get_session),
) -> List[DataPointRead]:
    try:
        return signal_service.list_datapoints_for_run(run_id, session, signal_family=signal_family)
    except SignalRunNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "RUN_NOT_FOUND", "detail": str(exc)},
        ) from exc


@router.get("/{run_id}/report", response_model=ActionReport)
def get_action_report(run_id: int, session: Session = Depends(get_session)) -> ActionReport:
    try:
        return ActionReportBuilder(session).build(run_id)
    except ActionReportRunNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "RUN_NOT_FOUND", "detail": str(exc)},
        ) from exc
