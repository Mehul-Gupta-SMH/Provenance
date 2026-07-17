"""Service layer for Experiment CRUD. Routes call these functions only.

v1 scope: create/get/list only (no update/delete — per task spec).
"""

from typing import List, Optional

from sqlmodel import Session, select

from provenance.models.experiment import Experiment, ExperimentCreate


def create_experiment(experiment_in: ExperimentCreate, session: Session) -> Experiment:
    experiment = Experiment(
        name=experiment_in.name,
        description=experiment_in.description,
        config_json=experiment_in.config_json,
    )
    session.add(experiment)
    session.commit()
    session.refresh(experiment)
    return experiment


def get_experiment(experiment_id: int, session: Session) -> Optional[Experiment]:
    return session.get(Experiment, experiment_id)


def list_experiments(session: Session, skip: int = 0, limit: int = 100) -> List[Experiment]:
    return session.exec(select(Experiment).offset(skip).limit(limit)).all()
