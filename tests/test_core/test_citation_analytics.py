"""Tests for provenance/core/citation_analytics.py.

Citations are constructed directly against the in-memory session (mirroring
tests/test_api/test_runs.py's citation tests) since there is no collector
seam for citation-domain analytics — this is pure read-time aggregation.
"""
from __future__ import annotations

import pytest

from provenance.core.citation_analytics import CitationAnalyticsEngine
from provenance.core.experiment_analysis import ExperimentNotFoundError
from provenance.models.citation import Citation
from provenance.models.experiment import Experiment
from provenance.models.query_probe import QueryProbe
from provenance.models.run import RunStatus
from provenance.services.signal_service import RunNotFoundError


def _add_citation(session, run, domain, content_type=None):
    probe = QueryProbe(run_id=run.id, query_variant="direct", query_text="q")
    session.add(probe)
    session.flush()
    session.add(
        Citation(
            entry_id=probe.id,
            cited_url=f"https://{domain}/page",
            domain=domain,
            content_type=content_type,
        )
    )
    session.commit()


def _make_experiment(session, name="exp-citations") -> Experiment:
    experiment = Experiment(name=name)
    session.add(experiment)
    session.commit()
    session.refresh(experiment)
    return experiment


def test_for_run_aggregates_domains_and_content_types(session, make_entity, make_run):
    entity = make_entity()
    run = make_run(entity.id, status=RunStatus.completed)

    _add_citation(session, run, "a.com", "docs")
    _add_citation(session, run, "a.com", "docs")
    _add_citation(session, run, "a.com", "blog")
    _add_citation(session, run, "b.com", None)
    _add_citation(session, run, "b.com", "review")
    _add_citation(session, run, "c.com", "forum")

    result = CitationAnalyticsEngine(session).for_run(run.id)

    assert result.scope == "run"
    assert result.scope_id == run.id
    assert result.total_citations == 6
    assert result.unique_domains == 3
    assert [d.domain for d in result.top_domains] == ["a.com", "b.com", "c.com"]
    assert [d.citation_count for d in result.top_domains] == [3, 2, 1]

    by_domain = {d.domain: d for d in result.top_domains}
    assert by_domain["a.com"].content_type_distribution == {"docs": 2, "blog": 1}
    assert by_domain["b.com"].content_type_distribution == {"unknown": 1, "review": 1}
    assert by_domain["c.com"].content_type_distribution == {"forum": 1}


def test_for_run_ties_sort_by_domain_ascending(session, make_entity, make_run):
    entity = make_entity()
    run = make_run(entity.id, status=RunStatus.completed)

    _add_citation(session, run, "zeta.com", "docs")
    _add_citation(session, run, "alpha.com", "docs")

    result = CitationAnalyticsEngine(session).for_run(run.id)

    assert [d.domain for d in result.top_domains] == ["alpha.com", "zeta.com"]


def test_for_run_unknown_run_raises(session):
    with pytest.raises(RunNotFoundError):
        CitationAnalyticsEngine(session).for_run(999999)


def test_for_run_empty_run_returns_zeros(session, make_entity, make_run):
    entity = make_entity()
    run = make_run(entity.id)

    result = CitationAnalyticsEngine(session).for_run(run.id)

    assert result.total_citations == 0
    assert result.unique_domains == 0
    assert result.top_domains == []


def test_for_experiment_unions_runs(session, make_entity, make_run):
    entity = make_entity()
    experiment = _make_experiment(session)
    run_a = make_run(entity.id, status=RunStatus.completed)
    run_b = make_run(entity.id, status=RunStatus.completed)
    run_a.experiment_id = experiment.id
    run_b.experiment_id = experiment.id
    session.add(run_a)
    session.add(run_b)
    session.commit()

    _add_citation(session, run_a, "a.com", "docs")
    _add_citation(session, run_b, "a.com", "blog")
    _add_citation(session, run_b, "b.com", "forum")

    result = CitationAnalyticsEngine(session).for_experiment(experiment.id)

    assert result.scope == "experiment"
    assert result.scope_id == experiment.id
    assert result.total_citations == 3
    assert result.unique_domains == 2
    by_domain = {d.domain: d for d in result.top_domains}
    assert by_domain["a.com"].citation_count == 2
    assert by_domain["a.com"].content_type_distribution == {"docs": 1, "blog": 1}
    assert by_domain["b.com"].citation_count == 1


def test_for_experiment_unknown_experiment_raises(session):
    with pytest.raises(ExperimentNotFoundError):
        CitationAnalyticsEngine(session).for_experiment(999999)


def test_for_experiment_empty_experiment_returns_zeros(session):
    experiment = _make_experiment(session)

    result = CitationAnalyticsEngine(session).for_experiment(experiment.id)

    assert result.total_citations == 0
    assert result.unique_domains == 0
    assert result.top_domains == []
