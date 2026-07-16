"""Tests for api/v1/routes/analysis.py (PLAN.md section 14, API 26-27)."""
from __future__ import annotations


def test_competitor_delta_returns_prioritized_result(client, make_entity, seed_completed_run):
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
    seed_completed_run(competitor.id, ranks_and_types=[(1, "primary", "positive", [])] * 4)

    response = client.post(
        "/v1/analysis/competitor-delta",
        json={"entity_id": entity.id, "competitor_entity_id": competitor.id},
    )

    assert response.status_code == 200
    body = response.json()
    by_field = {d["field"]: d for d in body["deltas"]}
    assert by_field["mention_rate"]["direction"] == "competitor_leads"
    assert "mention_rate" in body["summary_gap_fields"]


def test_gap_analysis_returns_sorted_gaps(client, make_entity, seed_completed_run):
    entity = make_entity(name="Acme")
    competitor = make_entity(name="Rival")
    seed_completed_run(
        entity.id,
        ranks_and_types=[(None, "absent", None, [])] * 4,
        search_volume=10.0,
    )
    seed_completed_run(
        competitor.id,
        ranks_and_types=[(1, "primary", "positive", [])] * 4,
        search_volume=90.0,
    )

    response = client.post(
        "/v1/analysis/gap",
        json={"entity_id": entity.id, "competitor_entity_id": competitor.id},
    )

    assert response.status_code == 200
    gaps = response.json()
    assert len(gaps) > 0
    priorities = [g["priority_score"] for g in gaps]
    assert priorities == sorted(priorities, reverse=True)


def test_competitor_delta_404_when_entity_missing(client, make_entity):
    competitor = make_entity(name="Rival")

    response = client.post(
        "/v1/analysis/competitor-delta",
        json={"entity_id": 999999, "competitor_entity_id": competitor.id},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "ENTITY_NOT_FOUND"


def test_competitor_delta_404_when_no_completed_run(client, make_entity):
    entity = make_entity(name="Acme")
    competitor = make_entity(name="Rival")

    response = client.post(
        "/v1/analysis/competitor-delta",
        json={"entity_id": entity.id, "competitor_entity_id": competitor.id},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "RUN_NOT_COMPLETED"


def test_gap_analysis_404_when_entity_missing(client, make_entity):
    competitor = make_entity(name="Rival")

    response = client.post(
        "/v1/analysis/gap",
        json={"entity_id": 999999, "competitor_entity_id": competitor.id},
    )

    assert response.status_code == 404
