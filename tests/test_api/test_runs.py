"""Tests for api/v1/routes/runs.py (PLAN.md section 14, API 23-25).

The background pipeline trigger is monkeypatched to a no-op: pipeline
orchestration itself is exercised independently and thoroughly in
tests/test_core/test_pipeline.py against a directly-constructed RunPipeline.
Here we only verify the route/service contract (status codes, response
shapes, structured 404s).
"""
from __future__ import annotations

import pytest

from provenance.api.v1.routes import runs as runs_module
from provenance.models.divergence_score import DivergenceScore
from provenance.models.run import RunStatus


@pytest.fixture(autouse=True)
def _stub_pipeline(monkeypatch):
    monkeypatch.setattr(runs_module, "_run_pipeline", lambda run_id, settings: None)


def test_create_run_missing_entity_returns_404(client):
    response = client.post("/v1/runs", json={"entity_id": 999999})

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "ENTITY_NOT_FOUND"


def test_create_run_missing_experiment_returns_404(client, make_entity):
    entity = make_entity()

    response = client.post(
        "/v1/runs", json={"entity_id": entity.id, "experiment_id": 999999}
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "EXPERIMENT_NOT_FOUND"


def test_create_run_returns_pending(client, make_entity):
    entity = make_entity()

    response = client.post("/v1/runs", json={"entity_id": entity.id})

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["entity_id"] == entity.id


def test_get_run_reflects_db_state(client, make_entity, make_run):
    entity = make_entity()
    run = make_run(entity.id, status=RunStatus.completed)

    response = client.get(f"/v1/runs/{run.id}")

    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_get_run_missing_returns_404(client):
    response = client.get("/v1/runs/999999")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "RUN_NOT_FOUND"


def test_get_divergence_returns_score(client, session, make_entity, make_run):
    entity = make_entity()
    run = make_run(entity.id, status=RunStatus.completed)
    score = DivergenceScore(
        run_id=run.id,
        entity_id=entity.id,
        demand_llm_alignment_score=0.8,
        divergence_direction="aligned",
        cross_query_stability=1.0,
        average_recommendation_rank=1.0,
        probes_included=4,
    )
    session.add(score)
    session.commit()

    response = client.get(f"/v1/runs/{run.id}/divergence")

    assert response.status_code == 200
    body = response.json()
    assert body["divergence_direction"] == "aligned"
    assert body["probes_included"] == 4


def test_get_divergence_missing_returns_404(client, make_entity, make_run):
    entity = make_entity()
    run = make_run(entity.id)

    response = client.get(f"/v1/runs/{run.id}/divergence")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "DIVERGENCE_NOT_FOUND"


def test_list_runs_filters_by_entity(client, make_entity, make_run):
    e1 = make_entity(name="Acme")
    e2 = make_entity(name="Other")
    make_run(e1.id)
    make_run(e2.id)

    response = client.get("/v1/runs", params={"entity_id": e1.id})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["entity_id"] == e1.id


def test_list_runs_pagination_params(client):
    assert client.get("/v1/runs", params={"limit": 0}).status_code == 422
    assert client.get("/v1/runs", params={"skip": -1}).status_code == 422
