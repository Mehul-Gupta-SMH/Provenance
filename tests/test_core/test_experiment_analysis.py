"""Tests for provenance/core/experiment_analysis.py.

Runs and DivergenceScore rows are constructed directly against the in-memory
session (mirroring tests/test_core/test_divergence.py); expected deltas are
computed by hand from the first- and last-completed run's scores.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from provenance.core.experiment_analysis import ExperimentAnalyzer, ExperimentNotFoundError
from provenance.models.divergence_score import DivergenceScore
from provenance.models.experiment import Experiment
from provenance.models.run import Run, RunStatus

_T0 = datetime(2026, 1, 1, 12, 0, 0)


def _make_experiment(session, name="exp-1") -> Experiment:
    experiment = Experiment(name=name)
    session.add(experiment)
    session.commit()
    session.refresh(experiment)
    return experiment


def _make_scored_run(session, entity_id, experiment_id, completed_at, alignment, rank, stability):
    run = Run(
        entity_id=entity_id,
        experiment_id=experiment_id,
        status=RunStatus.completed,
        completed_at=completed_at,
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    session.add(
        DivergenceScore(
            run_id=run.id,
            entity_id=entity_id,
            demand_llm_alignment_score=alignment,
            divergence_direction="aligned",
            cross_query_stability=stability,
            average_recommendation_rank=rank,
            mention_type_distribution_json='{"primary": 1}',
            probes_included=4,
        )
    )
    session.commit()
    return run


def test_compare_returns_ordered_snapshots_and_hand_computed_deltas(session, make_entity):
    entity = make_entity()
    experiment = _make_experiment(session)

    first = _make_scored_run(
        session, entity.id, experiment.id, _T0, alignment=0.3, rank=4.0, stability=0.5
    )
    last = _make_scored_run(
        session,
        entity.id,
        experiment.id,
        _T0 + timedelta(days=1),
        alignment=0.8,
        rank=1.5,
        stability=0.9,
    )
    failed = Run(
        entity_id=entity.id,
        experiment_id=experiment.id,
        status=RunStatus.failed,
    )
    session.add(failed)
    session.commit()
    session.refresh(failed)

    result = ExperimentAnalyzer(session).compare(experiment.id)

    assert result.experiment_id == experiment.id
    assert result.name == experiment.name
    assert [s.run_id for s in result.snapshots] == [first.id, last.id, failed.id]

    failed_snapshot = next(s for s in result.snapshots if s.run_id == failed.id)
    assert failed_snapshot.status == RunStatus.failed
    assert failed_snapshot.demand_llm_alignment_score is None
    assert failed_snapshot.average_recommendation_rank is None

    by_metric = {d.metric: d for d in result.deltas}
    assert by_metric["demand_llm_alignment_score"].first == 0.3
    assert by_metric["demand_llm_alignment_score"].last == 0.8
    assert by_metric["demand_llm_alignment_score"].delta == pytest.approx(0.5)
    assert by_metric["cross_query_stability"].delta == pytest.approx(0.4)
    assert by_metric["average_recommendation_rank"].delta == pytest.approx(-2.5)


def test_compare_fewer_than_two_scored_runs_has_no_deltas(session, make_entity):
    entity = make_entity()
    experiment = _make_experiment(session)
    _make_scored_run(session, entity.id, experiment.id, _T0, alignment=0.5, rank=2.0, stability=1.0)

    result = ExperimentAnalyzer(session).compare(experiment.id)

    assert len(result.snapshots) == 1
    assert result.deltas == []


def test_compare_unknown_experiment_raises_not_found(session):
    with pytest.raises(ExperimentNotFoundError):
        ExperimentAnalyzer(session).compare(999999)


def test_compare_empty_experiment_returns_empty_snapshots(session):
    experiment = _make_experiment(session)

    result = ExperimentAnalyzer(session).compare(experiment.id)

    assert result.snapshots == []
    assert result.deltas == []


def test_drift_returns_per_entity_time_ordered_series(session, make_entity):
    entity = make_entity()
    experiment = _make_experiment(session)

    first = _make_scored_run(
        session, entity.id, experiment.id, _T0, alignment=0.3, rank=4.0, stability=0.5
    )
    second = _make_scored_run(
        session,
        entity.id,
        experiment.id,
        _T0 + timedelta(days=1),
        alignment=0.8,
        rank=1.5,
        stability=0.9,
    )

    result = ExperimentAnalyzer(session).drift(experiment.id)

    assert result.experiment_id == experiment.id
    assert list(result.series.keys()) == [entity.id]
    points = result.series[entity.id]
    assert [p.run_id for p in points] == [first.id, second.id]
    assert points[0].demand_llm_alignment_score == 0.3
    assert points[1].demand_llm_alignment_score == 0.8


def test_drift_unknown_experiment_raises(session):
    with pytest.raises(ExperimentNotFoundError):
        ExperimentAnalyzer(session).drift(999999)


def test_drift_empty_experiment_returns_empty_series(session):
    experiment = _make_experiment(session)

    result = ExperimentAnalyzer(session).drift(experiment.id)

    assert result.series == {}
