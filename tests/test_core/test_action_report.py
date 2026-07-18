"""Tests for provenance/core/action_report.py.

seed_completed_run (conftest.py) covers QueryProbe/LLMSignal/DemandSignal/
DivergenceScore; citations and social DataPoints are seeded locally here since
those signal families aren't part of that shared fixture.
"""
from __future__ import annotations

import pytest
from sqlmodel import select

from provenance.core.action_report import ActionReportBuilder, RunNotFoundError
from provenance.models.citation import Citation
from provenance.models.data_point import DataPoint
from provenance.models.query_probe import QueryProbe


def _probes_for_run(session, run_id):
    return session.exec(select(QueryProbe).where(QueryProbe.run_id == run_id)).all()


def _add_citation(session, entry_id, content_type):
    session.add(
        Citation(
            entry_id=entry_id,
            cited_url="https://x.example.com",
            domain="x.example.com",
            content_type=content_type,
        )
    )
    session.commit()


def _add_social(session, run_id, story_count, points_total):
    session.add(
        DataPoint(
            run_id=run_id,
            signal_family="social",
            signal_key="hn_story_count",
            signal_value=story_count,
            collector_name="social",
        )
    )
    session.add(
        DataPoint(
            run_id=run_id,
            signal_family="social",
            signal_key="hn_points_total",
            signal_value=points_total,
            collector_name="social",
        )
    )
    session.commit()


def test_all_levers_fire_for_a_struggling_run(session, make_entity, seed_completed_run):
    """Low citations, zero HN, high demand, mostly-absent mentions -> all four levers."""
    entity = make_entity(name="Acme")
    run = seed_completed_run(
        entity.id,
        [
            (None, "absent", None, []),
            (None, "absent", None, ["Beta"]),
            (5, "alternative", "neutral", ["Beta", "Gamma"]),
        ],
        search_volume=80.0,
    )
    probes = _probes_for_run(session, run.id)
    entry_id = probes[0].id
    _add_citation(session, entry_id, content_type="blog")  # not comparison/docs
    _add_social(session, run.id, story_count=0.0, points_total=0.0)

    report = ActionReportBuilder(session).build(run.id)

    categories = {lever.category for lever in report.levers}
    assert categories == {"content", "social", "positioning", "demand"}
    # sorted priority desc
    assert [lever.priority_score for lever in report.levers] == sorted(
        (lever.priority_score for lever in report.levers), reverse=True
    )

    content_lever = next(lever for lever in report.levers if lever.category == "content")
    assert "0 comparison/docs citation" in content_lever.rationale

    social_lever = next(lever for lever in report.levers if lever.category == "social")
    assert "0 stor" in social_lever.rationale
    assert "0 total points" in social_lever.rationale

    positioning_lever = next(lever for lever in report.levers if lever.category == "positioning")
    assert "33.3%" in positioning_lever.rationale

    demand_lever = next(lever for lever in report.levers if lever.category == "demand")
    assert str(report.alignment_score) in demand_lever.rationale

    assert report.headline == "Strong real-world demand, under-recommended by the LLM"
    assert report.divergence_direction == "demand_ahead"


def test_competitor_pressure_aggregates_case_insensitively_and_excludes_self(
    session, make_entity, seed_completed_run
):
    entity = make_entity(name="Acme")
    run = seed_completed_run(
        entity.id,
        [
            (1, "primary", "positive", ["Beta", "acme", "Gamma"]),
            (2, "alternative", "neutral", ["beta", "Gamma"]),
            (3, "alternative", "neutral", ["Beta"]),
        ],
    )

    report = ActionReportBuilder(session).build(run.id)

    by_name = {cp.name.lower(): cp.times_co_mentioned for cp in report.competitor_pressure}
    assert by_name == {"beta": 3, "gamma": 2}
    assert "acme" not in by_name


def test_healthy_aligned_run_has_few_or_zero_levers(session, make_entity, seed_completed_run):
    entity = make_entity(name="Acme")
    run = seed_completed_run(
        entity.id,
        [
            (1, "primary", "positive", []),
            (1, "primary", "positive", []),
            (2, "primary", "positive", []),
        ],
        search_volume=90.0,
    )
    probes = _probes_for_run(session, run.id)
    for probe in probes:
        _add_citation(session, probe.id, content_type="comparison")
    _add_social(session, run.id, story_count=5.0, points_total=200.0)

    report = ActionReportBuilder(session).build(run.id)

    assert report.levers == []
    assert report.divergence_direction == "aligned"
    assert report.headline == "LLM recommendation is aligned with demand"
    assert "healthy" in report.summary.lower()


def test_run_with_no_divergence_and_no_signals_is_well_formed(session, make_entity, make_run):
    entity = make_entity()
    run = make_run(entity.id)

    report = ActionReportBuilder(session).build(run.id)

    assert report.headline == "Insufficient probe signal to assess"
    assert report.alignment_score is None
    assert report.divergence_direction is None
    assert report.levers == []
    assert report.competitor_pressure == []
    assert report.entity_id == entity.id
    assert report.entity_name == entity.name


def test_unknown_run_id_raises_run_not_found(session):
    with pytest.raises(RunNotFoundError):
        ActionReportBuilder(session).build(999999)
