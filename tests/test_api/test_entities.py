"""Tests for api/v1/routes/entities.py (PLAN.md section 14, API 21-22)."""
from __future__ import annotations


def test_create_entity_returns_201(client):
    response = client.post(
        "/v1/entities",
        json={
            "name": "Acme",
            "category": "graph database",
            "competitors": ["Rival"],
            "query_seeds": ["best graph db"],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Acme"
    assert body["competitors"] == ["Rival"]
    assert body["query_seeds"] == ["best graph db"]
    assert "id" in body


def test_get_entity_missing_returns_structured_404(client):
    response = client.get("/v1/entities/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == {
        "error": "ENTITY_NOT_FOUND",
        "detail": "Entity 999999 not found",
    }


def test_get_entity_found(client, make_entity):
    entity = make_entity(name="Acme")

    response = client.get(f"/v1/entities/{entity.id}")

    assert response.status_code == 200
    assert response.json()["name"] == "Acme"


def test_update_entity_round_trip(client, make_entity):
    entity = make_entity(name="Acme")

    response = client.patch(f"/v1/entities/{entity.id}", json={"category": "vector database"})

    assert response.status_code == 200
    assert response.json()["category"] == "vector database"


def test_update_entity_missing_returns_404(client):
    response = client.patch("/v1/entities/999999", json={"category": "x"})

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "ENTITY_NOT_FOUND"


def test_delete_entity(client, make_entity):
    entity = make_entity()

    response = client.delete(f"/v1/entities/{entity.id}")

    assert response.status_code == 200
    assert response.json() == {"deleted": True}
    assert client.get(f"/v1/entities/{entity.id}").status_code == 404


def test_delete_entity_missing_returns_404(client):
    response = client.delete("/v1/entities/999999")

    assert response.status_code == 404


def test_list_entities_pagination_params(client, make_entity):
    for i in range(3):
        make_entity(name=f"Entity{i}")

    ok = client.get("/v1/entities", params={"skip": 0, "limit": 2})
    assert ok.status_code == 200
    assert len(ok.json()) == 2

    assert client.get("/v1/entities", params={"skip": -1}).status_code == 422
    assert client.get("/v1/entities", params={"limit": 0}).status_code == 422
    assert client.get("/v1/entities", params={"limit": 1001}).status_code == 422


def test_entity_fingerprint_404_when_no_completed_run(client, make_entity):
    entity = make_entity()

    response = client.get(f"/v1/entities/{entity.id}/fingerprint")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "RUN_NOT_COMPLETED"


def test_entity_fingerprint_404_when_entity_missing(client):
    response = client.get("/v1/entities/999999/fingerprint")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "ENTITY_NOT_FOUND"
