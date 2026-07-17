"""Tests for CompetitorDelta (PLAN.md section 14, Analysis 18)."""
from __future__ import annotations

import pytest

from provenance.core.analysis import CompetitorDelta, EntityFingerprint, FingerprintBuilder


def _fp(entity_id, run_id, **overrides):
    base = dict(
        entity_id=entity_id,
        entity_name=f"entity-{entity_id}",
        run_id=run_id,
        search_volume=50.0,
        trend_velocity=0.0,
        average_recommendation_rank=2.0,
        mention_rate=0.5,
        primary_mention_rate=0.25,
        cross_query_stability=0.5,
        alignment_score=0.5,
    )
    base.update(overrides)
    return EntityFingerprint(**base)


def test_competitor_delta_entity_leads_on_rank_and_mention_rate():
    entity_fp = _fp(1, 10, mention_rate=0.8, average_recommendation_rank=1.0)
    competitor_fp = _fp(2, 20, mention_rate=0.3, average_recommendation_rank=3.0)

    result = CompetitorDelta().compute(entity_fp, competitor_fp)

    by_field = {d.field: d for d in result.deltas}
    assert by_field["mention_rate"].direction == "entity_leads"
    assert by_field["mention_rate"].delta == pytest.approx(0.5)
    # average_recommendation_rank is inverted: lower is better.
    assert by_field["average_recommendation_rank"].direction == "entity_leads"
    assert by_field["average_recommendation_rank"].delta == pytest.approx(-2.0)
    assert "mention_rate" in result.summary_advantage_fields
    assert "average_recommendation_rank" in result.summary_advantage_fields
    assert result.entity_id == 1
    assert result.competitor_entity_id == 2


def test_competitor_delta_competitor_leads_on_mention_rate():
    entity_fp = _fp(1, 10, mention_rate=0.2)
    competitor_fp = _fp(2, 20, mention_rate=0.9)

    result = CompetitorDelta().compute(entity_fp, competitor_fp)

    by_field = {d.field: d for d in result.deltas}
    assert by_field["mention_rate"].direction == "competitor_leads"
    assert "mention_rate" in result.summary_gap_fields


def test_competitor_delta_parity_within_threshold():
    entity_fp = _fp(1, 10, mention_rate=0.50)
    competitor_fp = _fp(2, 20, mention_rate=0.52)

    result = CompetitorDelta().compute(entity_fp, competitor_fp)

    by_field = {d.field: d for d in result.deltas}
    assert by_field["mention_rate"].direction == "parity"


def test_competitor_delta_two_seeded_entities(session, make_entity, seed_completed_run):
    """End-to-end: two seeded entities with completed runs, delta via FingerprintBuilder."""
    entity = make_entity(name="Acme")
    competitor = make_entity(name="Rival")

    seed_completed_run(
        entity.id,
        ranks_and_types=[
            (None, "absent", None, []),
            (None, "absent", None, []),
            (3, "alternative", "neutral", []),
            (3, "alternative", "neutral", []),
        ],
    )
    seed_completed_run(
        competitor.id,
        ranks_and_types=[(1, "primary", "positive", [])] * 4,
    )

    builder = FingerprintBuilder(session)
    entity_fp = builder.build(entity.id)
    competitor_fp = builder.build(competitor.id)

    result = CompetitorDelta().compute(entity_fp, competitor_fp)

    by_field = {d.field: d for d in result.deltas}
    assert by_field["mention_rate"].direction == "competitor_leads"
    assert "mention_rate" in result.summary_gap_fields
