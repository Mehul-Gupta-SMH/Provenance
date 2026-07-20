"""Tests for provenance/core/geo_score.py (docs/roadmap.md, "Composite 0-100
GEO score").

Rows are constructed directly against the in-memory session (DivergenceScore,
DataPoint, Citation, QueryProbe); expected GeoScore values are computed by
hand from the weights/caps documented in core/geo_score.py.
"""
from __future__ import annotations

import pytest

from provenance.core.geo_score import GeoScoreEngine, RunNotFoundError
from provenance.models.citation import Citation
from provenance.models.data_point import DataPoint
from provenance.models.divergence_score import DivergenceScore
from provenance.models.query_probe import QueryProbe
from provenance.models.run import Run, RunStatus


def _make_run(session, entity_id, n_probes=0):
    run = Run(entity_id=entity_id, status=RunStatus.completed)
    session.add(run)
    session.commit()
    session.refresh(run)

    probes = []
    for i in range(n_probes):
        qp = QueryProbe(run_id=run.id, query_variant="direct", query_text=f"q-{i}")
        session.add(qp)
        session.flush()
        probes.append(qp)
    session.commit()
    return run, probes


def test_geo_score_full_signal_set_matches_hand_computation(session, make_entity):
    entity = make_entity()
    run, probes = _make_run(session, entity.id, n_probes=4)

    session.add(
        DivergenceScore(
            run_id=run.id,
            entity_id=entity.id,
            demand_llm_alignment_score=0.6,
            divergence_direction="aligned",
            cross_query_stability=0.8,
            average_recommendation_rank=2.0,
            probes_included=4,
        )
    )
    session.add_all(
        [
            DataPoint(
                run_id=run.id,
                signal_family="content",
                signal_key="statistics_density",
                signal_value=5.0,
                collector_name="content",
            ),
            DataPoint(
                run_id=run.id,
                signal_family="content",
                signal_key="quotation_density",
                signal_value=2.5,
                collector_name="content",
            ),
            DataPoint(
                run_id=run.id,
                signal_family="content",
                signal_key="external_citation_density",
                signal_value=5.0,
                collector_name="content",
            ),
            DataPoint(
                run_id=run.id,
                signal_family="social",
                signal_key="hn_points_total",
                signal_value=100.0,
                collector_name="social",
            ),
        ]
    )
    for probe in probes[:2]:
        session.add(
            Citation(
                entry_id=probe.id,
                cited_url="https://acme.example.com/docs",
                domain="acme.example.com",
            )
        )
    session.commit()

    score = GeoScoreEngine(session).compute(run.id)

    by_name = {c.name: c for c in score.components}
    assert by_name["alignment"].normalized == 0.6
    assert by_name["alignment"].contribution == pytest.approx(15.0)
    assert by_name["stability"].normalized == 0.8
    assert by_name["stability"].contribution == pytest.approx(8.0)
    assert by_name["visibility"].normalized == pytest.approx(0.8)
    assert by_name["visibility"].contribution == pytest.approx(28.0)
    assert by_name["content_quality"].normalized == pytest.approx(0.5)
    assert by_name["content_quality"].contribution == pytest.approx(10.0)
    assert by_name["authority"].normalized == pytest.approx(0.5)
    assert by_name["authority"].contribution == pytest.approx(5.0)

    assert score.missing_signals == []
    assert score.geo_score == pytest.approx(66.0)
    assert score.band == "foundation"


def test_geo_score_only_divergence_present_marks_content_and_authority_missing(
    session, make_entity
):
    entity = make_entity()
    run, _probes = _make_run(session, entity.id, n_probes=0)

    session.add(
        DivergenceScore(
            run_id=run.id,
            entity_id=entity.id,
            demand_llm_alignment_score=0.9,
            divergence_direction="aligned",
            cross_query_stability=1.0,
            average_recommendation_rank=1.0,
            probes_included=0,
        )
    )
    session.commit()

    score = GeoScoreEngine(session).compute(run.id)

    assert set(score.missing_signals) == {"content_quality", "authority"}
    by_name = {c.name: c for c in score.components}
    assert by_name["content_quality"].normalized == 0.0
    assert by_name["authority"].normalized == 0.0
    assert by_name["alignment"].normalized == 0.9
    assert by_name["stability"].normalized == 1.0
    assert by_name["visibility"].normalized == 1.0
    assert score.geo_score == pytest.approx(67.5)
    assert score.band == "foundation"


def test_geo_score_no_signals_at_all_is_low_and_critical(session, make_entity):
    entity = make_entity()
    run, _probes = _make_run(session, entity.id, n_probes=0)

    score = GeoScoreEngine(session).compute(run.id)

    assert len(score.missing_signals) == 5
    assert score.geo_score == 0.0
    assert score.band == "critical"


def test_geo_score_unknown_run_raises_run_not_found_error(session):
    with pytest.raises(RunNotFoundError):
        GeoScoreEngine(session).compute(999999)
