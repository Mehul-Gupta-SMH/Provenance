"""Tests for GapAnalyzer (PLAN.md section 14, Analysis 19-20)."""
from __future__ import annotations

import pytest

from provenance.core.analysis import CompetitorDeltaResult, FieldDelta, GapAnalyzer


def _delta_result(deltas):
    return CompetitorDeltaResult(
        entity_id=1,
        competitor_entity_id=2,
        entity_run_id=10,
        competitor_run_id=20,
        deltas=deltas,
        summary_advantage_fields=[d.field for d in deltas if d.direction == "entity_leads"],
        summary_gap_fields=[d.field for d in deltas if d.direction == "competitor_leads"],
    )


def test_gap_analyzer_sorts_by_priority_score_descending():
    deltas = [
        FieldDelta(
            field="search_volume", entity_value=10, competitor_value=50,
            delta=-40, direction="competitor_leads",
        ),  # |delta|=40 * weight 0.5 = 20.0
        FieldDelta(
            field="mention_rate", entity_value=0.1, competitor_value=0.3,
            delta=-0.2, direction="competitor_leads",
        ),  # |delta|=0.2 * weight 0.9 = 0.18
        FieldDelta(
            field="average_recommendation_rank", entity_value=4.0, competitor_value=1.0,
            delta=3.0, direction="competitor_leads",
        ),  # |delta|=3.0 * weight 1.0 = 3.0
        FieldDelta(
            field="trend_velocity", entity_value=5.0, competitor_value=1.0,
            delta=4.0, direction="entity_leads",
        ),
    ]
    result = _delta_result(deltas)

    gaps = GapAnalyzer().analyze(result)

    assert [g.field for g in gaps] == [
        "search_volume",
        "average_recommendation_rank",
        "mention_rate",
    ]
    assert gaps[0].priority_score == 20.0
    assert gaps[1].priority_score == 3.0
    assert gaps[2].priority_score == pytest.approx(0.18)


def test_gap_analyzer_no_gaps_when_entity_leads_everywhere():
    deltas = [
        FieldDelta(
            field="mention_rate", entity_value=0.9, competitor_value=0.2,
            delta=0.7, direction="entity_leads",
        ),
        FieldDelta(
            field="search_volume", entity_value=80, competitor_value=79,
            delta=1, direction="parity",
        ),
    ]
    result = _delta_result(deltas)

    gaps = GapAnalyzer().analyze(result)

    assert gaps == []
