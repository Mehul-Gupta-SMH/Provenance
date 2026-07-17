"""Tests for the top-level /health endpoint (PLAN.md section 14, API)."""
from __future__ import annotations


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "1.0.0"}
