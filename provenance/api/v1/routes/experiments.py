"""Experiment CRUD routes (create/get/list only for v1), plus read-time analytics
(comparison/drift) and run-listing. No business logic here — analytics delegate to
core/experiment_analysis.py and run-listing delegates to experiment_service."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from provenance.core.experiment_analysis import (
    ExperimentAnalyzer,
    ExperimentComparison,
    ExperimentDrift,
    ExperimentNotFoundError,
)
from provenance.models.database import get_session
from provenance.models.experiment import Experiment, ExperimentCreate, ExperimentRead
from provenance.models.run import RunRead, run_to_read
from provenance.services import experiment_service

router = APIRouter(prefix="/experiments", tags=["experiments"])


def _not_found(experiment_id: int) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "error": "EXPERIMENT_NOT_FOUND",
            "detail": f"Experiment {experiment_id} not found",
        },
    )


@router.post("", response_model=ExperimentRead, status_code=201)
def create_experiment(
    experiment_in: ExperimentCreate, session: Session = Depends(get_session)
) -> Experiment:
    return experiment_service.create_experiment(experiment_in, session)


@router.get("", response_model=List[ExperimentRead])
def list_experiments(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    session: Session = Depends(get_session),
) -> List[Experiment]:
    return experiment_service.list_experiments(session, skip=skip, limit=limit)


@router.get("/{experiment_id}", response_model=ExperimentRead)
def get_experiment(experiment_id: int, session: Session = Depends(get_session)) -> Experiment:
    experiment = experiment_service.get_experiment(experiment_id, session)
    if experiment is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "EXPERIMENT_NOT_FOUND",
                "detail": f"Experiment {experiment_id} not found",
            },
        )
    return experiment


@router.get("/{experiment_id}/runs", response_model=List[RunRead])
def list_experiment_runs(
    experiment_id: int, session: Session = Depends(get_session)
) -> List[RunRead]:
    try:
        runs = experiment_service.list_runs_for_experiment(experiment_id, session)
    except experiment_service.ExperimentNotFoundError as exc:
        raise _not_found(experiment_id) from exc
    return [run_to_read(r) for r in runs]


@router.get("/{experiment_id}/comparison", response_model=ExperimentComparison)
def get_experiment_comparison(
    experiment_id: int, session: Session = Depends(get_session)
) -> ExperimentComparison:
    try:
        return ExperimentAnalyzer(session).compare(experiment_id)
    except ExperimentNotFoundError as exc:
        raise _not_found(experiment_id) from exc


@router.get("/{experiment_id}/drift", response_model=ExperimentDrift)
def get_experiment_drift(
    experiment_id: int, session: Session = Depends(get_session)
) -> ExperimentDrift:
    try:
        return ExperimentAnalyzer(session).drift(experiment_id)
    except ExperimentNotFoundError as exc:
        raise _not_found(experiment_id) from exc
