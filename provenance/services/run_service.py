"""Service layer for Run lifecycle (create/get/list).

v1 scope: this module only creates the Run record with status=pending and
reads it back. Pipeline execution (probes/collectors/divergence) is wired up
in a later phase — see the hook comment in api/v1/routes/runs.py.
"""

import json
from typing import List, Optional

from sqlmodel import Session, select

from provenance.models.entity import Entity
from provenance.models.experiment import Experiment
from provenance.models.run import Run, RunCreate, RunStatus


class EntityNotFoundError(Exception):
    """Raised when a Run references an entity_id that does not exist."""


class ExperimentNotFoundError(Exception):
    """Raised when a Run references an experiment_id that does not exist."""


def create_run(run_in: RunCreate, session: Session) -> Run:
    entity = session.get(Entity, run_in.entity_id)
    if entity is None:
        raise EntityNotFoundError(f"Entity {run_in.entity_id} not found")

    if run_in.experiment_id is not None:
        experiment = session.get(Experiment, run_in.experiment_id)
        if experiment is None:
            raise ExperimentNotFoundError(f"Experiment {run_in.experiment_id} not found")

    run = Run(
        entity_id=run_in.entity_id,
        experiment_id=run_in.experiment_id,
        mode=run_in.mode,
        status=RunStatus.pending,
        probe_contexts_json=json.dumps(
            [c.model_dump() for c in run_in.probe_contexts]
        ),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def get_run(run_id: int, session: Session) -> Optional[Run]:
    return session.get(Run, run_id)


def list_runs(
    session: Session,
    entity_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[Run]:
    statement = select(Run)
    if entity_id is not None:
        statement = statement.where(Run.entity_id == entity_id)
    statement = statement.offset(skip).limit(limit)
    return session.exec(statement).all()
