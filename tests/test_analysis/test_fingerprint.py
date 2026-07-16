"""Tests for FingerprintBuilder (PLAN.md section 14, Analysis 17)."""
from __future__ import annotations

import pytest

from provenance.core.analysis import EntityNotFoundError, FingerprintBuilder, NoCompletedRunError


def test_fingerprint_build_computes_expected_fields(session, make_entity, seed_completed_run):
    entity = make_entity(name="Acme", category="graph database")
    run = seed_completed_run(
        entity.id,
        ranks_and_types=[
            (1, "primary", "positive", ["Rival"]),
            (2, "alternative", "positive", ["Rival"]),
            (None, "absent", None, []),
            (1, "primary", "neutral", ["Rival", "Other"]),
        ],
        search_volume=80.0,
        trend_velocity=10.0,
        related_queries=["acme pricing"],
        geographic_distribution={"US": 90.0},
    )

    fp = FingerprintBuilder(session).build(entity.id)

    assert fp.entity_id == entity.id
    assert fp.entity_name == "Acme"
    assert fp.run_id == run.id
    assert fp.search_volume == 80.0
    assert fp.trend_velocity == 10.0
    assert fp.related_queries == ["acme pricing"]
    assert fp.geographic_distribution == {"US": 90.0}
    # avg rank over the 3 non-null ranks: (1 + 2 + 1) / 3
    assert fp.average_recommendation_rank == pytest.approx(4 / 3)
    assert fp.mention_rate == pytest.approx(3 / 4)  # 3 of 4 signals not "absent"
    assert fp.primary_mention_rate == pytest.approx(2 / 4)  # 2 "primary" signals
    assert fp.phrasing_sentiment_distribution == {
        "positive": pytest.approx(2 / 4),
        "neutral": pytest.approx(1 / 4),
    }
    assert fp.top_co_mentioned[:1] == ["Rival"]  # co-mentioned in 3 of 4 signals
    # Hand-computed from core/divergence.py's formula for this exact input:
    # ranks=[1,2,6,1] (absent -> penalty 6), avg=2.5, rank_score=0.625,
    # mention_rate=0.75, search_volume_normalized=0.8
    # alignment = 0.8*0.4 + 0.625*0.4 + 0.75*0.2 = 0.72 -> "aligned"
    # stability: range(6-1)=5 -> 1 - 5/5 = 0.0
    assert fp.alignment_score == 0.72
    assert fp.divergence_direction == "aligned"
    assert fp.cross_query_stability == 0.0


def test_fingerprint_entity_not_found_raises(session):
    with pytest.raises(EntityNotFoundError):
        FingerprintBuilder(session).build(999999)


def test_fingerprint_no_completed_run_raises(session, make_entity):
    entity = make_entity()
    with pytest.raises(NoCompletedRunError):
        FingerprintBuilder(session).build(entity.id)


def test_fingerprint_specific_run_id_not_completed_raises(session, make_entity, make_run):
    entity = make_entity()
    run = make_run(entity.id)  # defaults to RunStatus.pending

    with pytest.raises(NoCompletedRunError):
        FingerprintBuilder(session).build(entity.id, run_id=run.id)
