"""Tests for the experiment analytics/run-listing routes added to
api/v1/routes/experiments.py: GET /experiments/{id}/runs, /comparison, /drift.
"""
from __future__ import annotations

from datetime import datetime

from provenance.models.run import RunStatus


def _attach_to_experiment(session, run, experiment_id, completed_at=None):
    run.experiment_id = experiment_id
    if completed_at is not None:
        run.completed_at = completed_at
    session.add(run)
    session.commit()


def test_list_experiment_runs_returns_all_runs(
    client, session, make_entity, make_run, seed_completed_run
):
    entity = make_entity()
    experiment = client.post("/v1/experiments", json={"name": "exp-runs"}).json()

    run_a = seed_completed_run(entity.id, ranks_and_types=[(1, "primary", "positive", [])] * 4)
    run_b = seed_completed_run(entity.id, ranks_and_types=[(3, "alternative", "neutral", [])] * 4)
    run_c = make_run(entity.id, status=RunStatus.failed)
    for r in (run_a, run_b, run_c):
        _attach_to_experiment(session, r, experiment["id"])

    response = client.get(f"/v1/experiments/{experiment['id']}/runs")

    assert response.status_code == 200
    ids = {r["id"] for r in response.json()}
    assert ids == {run_a.id, run_b.id, run_c.id}


def test_comparison_returns_snapshots_and_deltas_with_failed_run_untouched(
    client, session, make_entity, make_run, seed_completed_run
):
    entity = make_entity()
    experiment = client.post("/v1/experiments", json={"name": "exp-comparison"}).json()

    run_a = seed_completed_run(entity.id, ranks_and_types=[(None, "absent", None, [])] * 4)
    run_b = seed_completed_run(entity.id, ranks_and_types=[(1, "primary", "positive", [])] * 4)
    run_c = make_run(entity.id, status=RunStatus.failed)
    _attach_to_experiment(session, run_a, experiment["id"], datetime(2026, 1, 1))
    _attach_to_experiment(session, run_b, experiment["id"], datetime(2026, 1, 2))
    _attach_to_experiment(session, run_c, experiment["id"])

    response = client.get(f"/v1/experiments/{experiment['id']}/comparison")

    assert response.status_code == 200
    body = response.json()
    assert body["experiment_id"] == experiment["id"]
    assert [s["run_id"] for s in body["snapshots"]] == [run_a.id, run_b.id, run_c.id]

    failed_snapshot = next(s for s in body["snapshots"] if s["run_id"] == run_c.id)
    assert failed_snapshot["status"] == "failed"
    assert failed_snapshot["demand_llm_alignment_score"] is None

    by_metric = {d["metric"]: d for d in body["deltas"]}
    assert by_metric["demand_llm_alignment_score"]["delta"] > 0


def test_drift_returns_time_ordered_series_for_entity(
    client, session, make_entity, seed_completed_run
):
    entity = make_entity()
    experiment = client.post("/v1/experiments", json={"name": "exp-drift"}).json()

    run_a = seed_completed_run(entity.id, ranks_and_types=[(None, "absent", None, [])] * 4)
    run_b = seed_completed_run(entity.id, ranks_and_types=[(1, "primary", "positive", [])] * 4)
    _attach_to_experiment(session, run_a, experiment["id"], datetime(2026, 1, 1))
    _attach_to_experiment(session, run_b, experiment["id"], datetime(2026, 1, 2))

    response = client.get(f"/v1/experiments/{experiment['id']}/drift")

    assert response.status_code == 200
    body = response.json()
    series = body["series"][str(entity.id)]
    assert [p["run_id"] for p in series] == [run_a.id, run_b.id]
    assert series[0]["demand_llm_alignment_score"] < series[1]["demand_llm_alignment_score"]


def test_unknown_experiment_404s_on_all_three_endpoints(client):
    for path in ("runs", "comparison", "drift"):
        response = client.get(f"/v1/experiments/999999/{path}")
        assert response.status_code == 404
        assert response.json()["detail"]["error"] == "EXPERIMENT_NOT_FOUND"


def test_empty_experiment_returns_empty_payloads(client):
    experiment = client.post("/v1/experiments", json={"name": "exp-empty"}).json()

    runs_resp = client.get(f"/v1/experiments/{experiment['id']}/runs")
    comparison_resp = client.get(f"/v1/experiments/{experiment['id']}/comparison")
    drift_resp = client.get(f"/v1/experiments/{experiment['id']}/drift")

    assert runs_resp.status_code == 200
    assert runs_resp.json() == []
    assert comparison_resp.status_code == 200
    assert comparison_resp.json()["snapshots"] == []
    assert comparison_resp.json()["deltas"] == []
    assert drift_resp.status_code == 200
    assert drift_resp.json()["series"] == {}


# ---------------------------------------------------------------------------
# Citation-domain analytics endpoint: GET /experiments/{id}/citation-analytics
# ---------------------------------------------------------------------------


def test_get_experiment_citation_analytics_unions_runs(
    client, session, make_entity, make_run
):
    from provenance.models.citation import Citation
    from provenance.models.query_probe import QueryProbe

    entity = make_entity()
    experiment = client.post("/v1/experiments", json={"name": "exp-citation-analytics"}).json()
    run_a = make_run(entity.id)
    run_b = make_run(entity.id)
    _attach_to_experiment(session, run_a, experiment["id"])
    _attach_to_experiment(session, run_b, experiment["id"])

    for run, domain, content_type in [
        (run_a, "acme.example.com", "docs"),
        (run_b, "acme.example.com", "blog"),
        (run_b, "other.example.com", "forum"),
    ]:
        probe = QueryProbe(run_id=run.id, query_variant="direct", query_text="q")
        session.add(probe)
        session.flush()
        session.add(
            Citation(
                entry_id=probe.id,
                cited_url=f"https://{domain}/x",
                domain=domain,
                content_type=content_type,
            )
        )
    session.commit()

    response = client.get(f"/v1/experiments/{experiment['id']}/citation-analytics")

    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "experiment"
    assert body["scope_id"] == experiment["id"]
    assert body["total_citations"] == 3
    assert body["unique_domains"] == 2
    top = {d["domain"]: d for d in body["top_domains"]}
    assert top["acme.example.com"]["citation_count"] == 2
    assert top["acme.example.com"]["content_type_distribution"] == {"docs": 1, "blog": 1}


def test_get_experiment_citation_analytics_missing_experiment_returns_404(client):
    response = client.get("/v1/experiments/999999/citation-analytics")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "EXPERIMENT_NOT_FOUND"


def test_get_experiment_citation_analytics_empty_experiment_returns_zeros(client):
    experiment = client.post("/v1/experiments", json={"name": "exp-citation-empty"}).json()

    response = client.get(f"/v1/experiments/{experiment['id']}/citation-analytics")

    assert response.status_code == 200
    body = response.json()
    assert body["total_citations"] == 0
    assert body["unique_domains"] == 0
    assert body["top_domains"] == []
