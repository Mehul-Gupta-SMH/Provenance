"""Experiment CRUD routes (create/get/list only for v1). No business logic here."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from provenance.models.database import get_session
from provenance.models.experiment import Experiment, ExperimentCreate, ExperimentRead
from provenance.services import experiment_service

router = APIRouter(prefix="/experiments", tags=["experiments"])


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
