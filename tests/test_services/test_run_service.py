"""Tests for provenance/services/run_service.py (PLAN.md section 14, Services)."""
from __future__ import annotations

import pytest

from provenance.models.entity import EntityCreate
from provenance.models.experiment import ExperimentCreate
from provenance.models.run import RunCreate, RunMode, RunStatus
from provenance.services import entity_service, experiment_service, run_service


def test_create_run_missing_entity_raises(session):
    with pytest.raises(run_service.EntityNotFoundError):
        run_service.create_run(RunCreate(entity_id=999999), session)


def test_create_run_missing_experiment_raises(session):
    entity = entity_service.create_entity(
        EntityCreate(name="Acme", category="graph database"), session
    )

    with pytest.raises(run_service.ExperimentNotFoundError):
        run_service.create_run(
            RunCreate(entity_id=entity.id, experiment_id=999999), session
        )


def test_create_run_success_defaults_to_pending(session):
    entity = entity_service.create_entity(
        EntityCreate(name="Acme", category="graph database"), session
    )

    run = run_service.create_run(RunCreate(entity_id=entity.id), session)

    assert run.id is not None
    assert run.status == RunStatus.pending
    assert run.mode == RunMode.isolation
    assert run.experiment_id is None


def test_create_run_with_experiment(session):
    entity = entity_service.create_entity(
        EntityCreate(name="Acme", category="graph database"), session
    )
    experiment = experiment_service.create_experiment(
        ExperimentCreate(name="baseline-2026-q1"), session
    )

    run = run_service.create_run(
        RunCreate(entity_id=entity.id, experiment_id=experiment.id), session
    )

    assert run.experiment_id == experiment.id


def test_get_and_list_runs(session):
    entity = entity_service.create_entity(
        EntityCreate(name="Acme", category="graph database"), session
    )
    other = entity_service.create_entity(
        EntityCreate(name="Other", category="graph database"), session
    )
    run1 = run_service.create_run(RunCreate(entity_id=entity.id), session)
    run_service.create_run(RunCreate(entity_id=other.id), session)

    fetched = run_service.get_run(run1.id, session)
    assert fetched is not None
    assert fetched.entity_id == entity.id

    assert run_service.get_run(999999, session) is None

    filtered = run_service.list_runs(session, entity_id=entity.id)
    assert len(filtered) == 1
    assert filtered[0].entity_id == entity.id

    all_runs = run_service.list_runs(session)
    assert len(all_runs) == 2
