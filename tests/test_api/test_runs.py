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


# ---------------------------------------------------------------------------
# Context sweep: probe_contexts on RunCreate/RunRead
# ---------------------------------------------------------------------------


def test_create_run_with_probe_contexts_stores_and_returns_specs(client, make_entity):
    entity = make_entity()

    response = client.post(
        "/v1/runs",
        json={
            "entity_id": entity.id,
            "probe_contexts": [
                {"user_persona": "developer", "temperature": 0.1},
                {"user_persona": "executive", "locale": "en-GB"},
            ],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert len(body["probe_contexts"]) == 2
    assert body["probe_contexts"][0]["user_persona"] == "developer"
    assert body["probe_contexts"][0]["temperature"] == 0.1
    assert body["probe_contexts"][1]["locale"] == "en-GB"

    get_response = client.get(f"/v1/runs/{body['id']}")
    assert get_response.status_code == 200
    assert len(get_response.json()["probe_contexts"]) == 2


def test_create_run_without_probe_contexts_returns_empty_list(client, make_entity):
    entity = make_entity()

    response = client.post("/v1/runs", json={"entity_id": entity.id})

    assert response.status_code == 201
    assert response.json()["probe_contexts"] == []


def test_create_run_too_many_probe_contexts_returns_422(client, make_entity):
    entity = make_entity()

    response = client.post(
        "/v1/runs",
        json={
            "entity_id": entity.id,
            "probe_contexts": [{"user_persona": f"persona-{i}"} for i in range(11)],
        },
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Signal-read endpoints (PLAN.md section 12): probes, signals, citations, demand
# ---------------------------------------------------------------------------


def test_list_probes_for_run_returns_rows(client, make_entity, seed_completed_run):
    entity = make_entity()
    run = seed_completed_run(
        entity.id,
        [(1, "primary", "positive", []), (2, "alternative", "neutral", [])],
    )

    response = client.get(f"/v1/runs/{run.id}/probes")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert {p["query_variant"] for p in body} == {"direct", "comparative"}
    assert all(p["run_id"] == run.id for p in body)


def test_list_signals_for_run_deserializes_co_mentioned(
    client, make_entity, seed_completed_run
):
    entity = make_entity()
    run = seed_completed_run(
        entity.id, [(1, "primary", "positive", ["Beta", "Gamma"])]
    )

    response = client.get(f"/v1/runs/{run.id}/signals")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["co_mentioned_entities"] == ["Beta", "Gamma"]
    assert body[0]["mention_type"] == "primary"


def test_list_citations_for_run_returns_rows(client, session, make_entity, make_run):
    from provenance.models.citation import Citation
    from provenance.models.query_probe import QueryProbe

    entity = make_entity()
    run = make_run(entity.id)
    probe = QueryProbe(run_id=run.id, query_variant="direct", query_text="q")
    session.add(probe)
    session.flush()
    session.add(
        Citation(
            entry_id=probe.id,
            cited_url="https://acme.example.com/docs",
            domain="acme.example.com",
        )
    )
    session.commit()

    response = client.get(f"/v1/runs/{run.id}/citations")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["cited_url"] == "https://acme.example.com/docs"
    assert body[0]["entry_id"] == probe.id


def test_list_demand_for_run_deserializes_json_fields(
    client, make_entity, seed_completed_run
):
    entity = make_entity()
    run = seed_completed_run(
        entity.id,
        [(1, "primary", "positive", [])],
        related_queries=["acme guide", "acme pricing"],
        geographic_distribution={"US": 90.0, "IN": 10.0},
    )

    response = client.get(f"/v1/runs/{run.id}/demand")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["related_queries"] == ["acme guide", "acme pricing"]
    assert body[0]["geographic_distribution"] == {"US": 90.0, "IN": 10.0}


def test_signal_endpoints_empty_run_returns_empty_list(client, make_entity, make_run):
    entity = make_entity()
    run = make_run(entity.id)

    for path in ("probes", "signals", "citations", "demand"):
        response = client.get(f"/v1/runs/{run.id}/{path}")
        assert response.status_code == 200
        assert response.json() == []


def test_signal_endpoints_missing_run_returns_404(client):
    for path in ("probes", "signals", "citations", "demand"):
        response = client.get(f"/v1/runs/999999/{path}")
        assert response.status_code == 404
        assert response.json()["detail"]["error"] == "RUN_NOT_FOUND"


# ---------------------------------------------------------------------------
# DataPoint read endpoint: GET /runs/{run_id}/datapoints
# ---------------------------------------------------------------------------


def test_list_datapoints_for_run_returns_rows(client, session, make_entity, make_run):
    from provenance.models.data_point import DataPoint

    entity = make_entity()
    run = make_run(entity.id)
    session.add(
        DataPoint(
            run_id=run.id,
            signal_family="social",
            signal_key="hn_story_count",
            signal_value=3.0,
            collector_name="social",
        )
    )
    session.add(
        DataPoint(
            run_id=run.id,
            signal_family="other",
            signal_key="something_else",
            signal_value=1.0,
            collector_name="other",
        )
    )
    session.commit()

    response = client.get(f"/v1/runs/{run.id}/datapoints")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert all(dp["run_id"] == run.id for dp in body)
    assert all(dp["entry_id"] is None for dp in body)


def test_list_datapoints_for_run_filters_by_signal_family(client, session, make_entity, make_run):
    from provenance.models.data_point import DataPoint

    entity = make_entity()
    run = make_run(entity.id)
    session.add(
        DataPoint(
            run_id=run.id,
            signal_family="social",
            signal_key="hn_story_count",
            signal_value=3.0,
            collector_name="social",
        )
    )
    session.add(
        DataPoint(
            run_id=run.id,
            signal_family="other",
            signal_key="something_else",
            signal_value=1.0,
            collector_name="other",
        )
    )
    session.commit()

    response = client.get(f"/v1/runs/{run.id}/datapoints", params={"signal_family": "social"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["signal_key"] == "hn_story_count"


def test_list_datapoints_for_run_missing_run_returns_404(client):
    response = client.get("/v1/runs/999999/datapoints")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "RUN_NOT_FOUND"


# ---------------------------------------------------------------------------
# Action report endpoint: GET /runs/{run_id}/report
# ---------------------------------------------------------------------------


def test_get_action_report_returns_report_for_completed_run(
    client, make_entity, seed_completed_run
):
    entity = make_entity(name="Acme")
    run = seed_completed_run(
        entity.id,
        [(1, "primary", "positive", ["Beta"])],
        search_volume=90.0,
    )

    response = client.get(f"/v1/runs/{run.id}/report")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == run.id
    assert body["entity_id"] == entity.id
    assert body["entity_name"] == "Acme"
    assert "headline" in body
    assert isinstance(body["levers"], list)
    assert isinstance(body["competitor_pressure"], list)


def test_get_action_report_missing_run_returns_404(client):
    response = client.get("/v1/runs/999999/report")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "RUN_NOT_FOUND"
