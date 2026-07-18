"""Tests for provenance/core/pipeline.py (PLAN.md section 14, Pipeline 9-12).

AnthropicProbe.probe and DemandCollector.collect are monkeypatched at the class
level so no network access or ANTHROPIC_API_KEY is required. CitationExtractor
is real (pure text processing).
"""
from __future__ import annotations

import json

import pytest
from sqlmodel import select

from provenance.collectors.demand import DemandCollector
from provenance.collectors.social import SocialCollector
from provenance.core.pipeline import RunPipeline
from provenance.core.registry import CollectorRegistry, ProbeRegistry
from provenance.models.citation import Citation
from provenance.models.data_point import DataPoint
from provenance.models.demand_signal import DemandSignal
from provenance.models.divergence_score import DivergenceScore
from provenance.models.llm_signal import LLMSignal
from provenance.models.query_probe import QueryProbe
from provenance.models.run import Run, RunStatus
from provenance.probes.anthropic import AnthropicProbe


@pytest.fixture(autouse=True)
def _register_real_classes():
    """RunPipeline resolves probes/collectors via the registries — register the
    real classes (methods are monkeypatched per-test) since main.py's startup
    hook that normally does this doesn't run for these core-level tests."""
    ProbeRegistry.register("anthropic", AnthropicProbe)
    CollectorRegistry.register("demand", DemandCollector)
    CollectorRegistry.register("social", SocialCollector)


@pytest.fixture(autouse=True)
def _stub_social_collector(monkeypatch):
    """Default social collector stub (no rows) so pre-existing pipeline tests
    that don't care about social signals stay network-free. Tests exercising
    social behavior override this with their own monkeypatch."""
    monkeypatch.setattr(SocialCollector, "collect", lambda self, entity_name: [])


async def test_pipeline_completed_run_writes_expected_rows(
    session, test_settings, monkeypatch, make_entity, make_run, make_probe_result,
    make_demand_result, make_extracted_entity,
):
    entity = make_entity(name="Acme", category="graph database", competitors=["Rival"])
    run = make_run(entity.id)

    own = make_extracted_entity(name="Acme", recommendation_rank=1, mention_type="primary")
    competitor = make_extracted_entity(
        name="Rival", recommendation_rank=2, mention_type="alternative"
    )

    async def fake_probe(self, query, query_variant, entity_name, context, competitors=None):
        return make_probe_result(
            query_variant=query_variant,
            raw_response=f"{entity_name} is great. See https://acme.example.com/{query_variant}.",
            extracted_entities=[own, competitor],
        )

    def fake_collect(self, entity_name, category):
        return make_demand_result(entity_name=entity_name)

    monkeypatch.setattr(AnthropicProbe, "probe", fake_probe)
    monkeypatch.setattr(DemandCollector, "collect", fake_collect)

    pipeline = RunPipeline(settings=test_settings, session=session)
    await pipeline.execute(run.id)

    session.refresh(run)
    assert run.status == RunStatus.completed
    assert run.error_message is None

    probes = session.exec(select(QueryProbe).where(QueryProbe.run_id == run.id)).all()
    assert len(probes) == 4
    assert {p.query_variant for p in probes} == {
        "direct", "comparative", "expert", "contrarian",
    }

    entry_ids = [p.id for p in probes]
    signals = session.exec(select(LLMSignal).where(LLMSignal.entry_id.in_(entry_ids))).all()
    assert len(signals) == 4
    for sig in signals:
        assert sig.entry_id in entry_ids
        assert sig.recommendation_rank == 1
        assert sig.mention_type == "primary"
        assert json.loads(sig.co_mentioned_entities_json) == ["Rival"]

    demand_signals = session.exec(
        select(DemandSignal).where(DemandSignal.run_id == run.id)
    ).all()
    assert len(demand_signals) == 1

    citations = session.exec(select(Citation).where(Citation.entry_id.in_(entry_ids))).all()
    assert len(citations) == 4

    divergence = session.exec(
        select(DivergenceScore).where(DivergenceScore.run_id == run.id)
    ).first()
    assert divergence is not None
    assert divergence.probes_included == 4


async def test_pipeline_all_probes_fail_marks_run_failed(
    session, test_settings, monkeypatch, make_entity, make_run, make_probe_result,
    make_demand_result,
):
    entity = make_entity(name="Acme", category="graph database")
    run = make_run(entity.id)

    async def fake_probe_error(self, query, query_variant, entity_name, context, competitors=None):
        return make_probe_result(
            query_variant=query_variant, raw_response="", extracted_entities=[], error="boom"
        )

    def fake_collect(self, entity_name, category):
        return make_demand_result(entity_name=entity_name)

    monkeypatch.setattr(AnthropicProbe, "probe", fake_probe_error)
    monkeypatch.setattr(DemandCollector, "collect", fake_collect)

    pipeline = RunPipeline(settings=test_settings, session=session)
    await pipeline.execute(run.id)

    session.refresh(run)
    assert run.status == RunStatus.failed
    assert run.error_message is not None

    divergence = session.exec(
        select(DivergenceScore).where(DivergenceScore.run_id == run.id)
    ).first()
    assert divergence is None


async def test_pipeline_partial_failure_still_completes(
    session, test_settings, monkeypatch, make_entity, make_run, make_probe_result,
    make_demand_result, make_extracted_entity,
):
    entity = make_entity(name="Acme", category="graph database")
    run = make_run(entity.id)
    own = make_extracted_entity(name="Acme", recommendation_rank=1, mention_type="primary")

    async def fake_probe_partial(
        self, query, query_variant, entity_name, context, competitors=None
    ):
        if query_variant == "contrarian":
            return make_probe_result(
                query_variant=query_variant,
                raw_response="",
                extracted_entities=[],
                error="timeout",
            )
        return make_probe_result(
            query_variant=query_variant,
            raw_response=f"{entity_name} is solid.",
            extracted_entities=[own],
        )

    def fake_collect(self, entity_name, category):
        return make_demand_result(entity_name=entity_name)

    monkeypatch.setattr(AnthropicProbe, "probe", fake_probe_partial)
    monkeypatch.setattr(DemandCollector, "collect", fake_collect)

    pipeline = RunPipeline(settings=test_settings, session=session)
    await pipeline.execute(run.id)

    session.refresh(run)
    assert run.status == RunStatus.completed

    divergence = session.exec(
        select(DivergenceScore).where(DivergenceScore.run_id == run.id)
    ).first()
    assert divergence is not None
    # the "contrarian" probe soft-failed and is excluded from probes_included
    assert divergence.probes_included == 3


async def test_pipeline_probe_contexts_fan_out_produces_matrix(
    session, test_settings, monkeypatch, make_entity, make_run, make_probe_result,
    make_demand_result, make_extracted_entity,
):
    """2 probe_contexts x 4 variants -> 8 QueryProbe rows with distinct persona/
    temperature values in the flat columns, and 8 LLMSignals."""
    import json as _json

    from provenance.models.run import ProbeContextSpec

    entity = make_entity(name="Acme", category="graph database")
    run = make_run(entity.id)
    run.probe_contexts_json = _json.dumps([
        ProbeContextSpec(user_persona="developer", temperature=0.1).model_dump(),
        ProbeContextSpec(user_persona="executive", temperature=0.9).model_dump(),
    ])
    session.add(run)
    session.commit()

    own = make_extracted_entity(name="Acme", recommendation_rank=1, mention_type="primary")

    async def fake_probe(self, query, query_variant, entity_name, context, competitors=None):
        return make_probe_result(
            query_variant=query_variant,
            raw_response=f"{entity_name} is great.",
            extracted_entities=[own],
        )

    def fake_collect(self, entity_name, category):
        return make_demand_result(entity_name=entity_name)

    monkeypatch.setattr(AnthropicProbe, "probe", fake_probe)
    monkeypatch.setattr(DemandCollector, "collect", fake_collect)

    pipeline = RunPipeline(settings=test_settings, session=session)
    await pipeline.execute(run.id)

    session.refresh(run)
    assert run.status == RunStatus.completed

    probes = session.exec(select(QueryProbe).where(QueryProbe.run_id == run.id)).all()
    assert len(probes) == 8

    personas_and_temps = {(p.user_persona, p.temperature) for p in probes}
    assert personas_and_temps == {("developer", 0.1), ("executive", 0.9)}

    entry_ids = [p.id for p in probes]
    signals = session.exec(select(LLMSignal).where(LLMSignal.entry_id.in_(entry_ids))).all()
    assert len(signals) == 8


async def test_pipeline_empty_probe_contexts_matches_today_default(
    session, test_settings, monkeypatch, make_entity, make_run, make_probe_result,
    make_demand_result, make_extracted_entity,
):
    """Empty probe_contexts (today's default RunCreate) -> exactly today's 4 rows."""
    entity = make_entity(name="Acme", category="graph database")
    run = make_run(entity.id)
    assert run.probe_contexts_json == "[]"

    own = make_extracted_entity(name="Acme", recommendation_rank=1, mention_type="primary")

    async def fake_probe(self, query, query_variant, entity_name, context, competitors=None):
        return make_probe_result(
            query_variant=query_variant,
            raw_response=f"{entity_name} is great.",
            extracted_entities=[own],
        )

    def fake_collect(self, entity_name, category):
        return make_demand_result(entity_name=entity_name)

    monkeypatch.setattr(AnthropicProbe, "probe", fake_probe)
    monkeypatch.setattr(DemandCollector, "collect", fake_collect)

    pipeline = RunPipeline(settings=test_settings, session=session)
    await pipeline.execute(run.id)

    session.refresh(run)
    assert run.status == RunStatus.completed

    probes = session.exec(select(QueryProbe).where(QueryProbe.run_id == run.id)).all()
    assert len(probes) == 4
    for p in probes:
        assert p.user_persona is None
        assert p.temperature == test_settings.anthropic_default_temperature


async def test_pipeline_mixed_context_partial_failure_keeps_run_completed(
    session, test_settings, monkeypatch, make_entity, make_run, make_probe_result,
    make_demand_result, make_extracted_entity,
):
    """One context's probes all error, the other context's probes succeed ->
    run still completes since not ALL probes across the matrix failed."""
    import json as _json

    from provenance.models.run import ProbeContextSpec

    entity = make_entity(name="Acme", category="graph database")
    run = make_run(entity.id)
    run.probe_contexts_json = _json.dumps([
        ProbeContextSpec(user_persona="developer").model_dump(),
        ProbeContextSpec(user_persona="executive").model_dump(),
    ])
    session.add(run)
    session.commit()

    own = make_extracted_entity(name="Acme", recommendation_rank=1, mention_type="primary")

    async def fake_probe(self, query, query_variant, entity_name, context, competitors=None):
        if context.user_persona == "executive":
            return make_probe_result(
                query_variant=query_variant, raw_response="", extracted_entities=[], error="boom"
            )
        return make_probe_result(
            query_variant=query_variant,
            raw_response=f"{entity_name} is great.",
            extracted_entities=[own],
        )

    def fake_collect(self, entity_name, category):
        return make_demand_result(entity_name=entity_name)

    monkeypatch.setattr(AnthropicProbe, "probe", fake_probe)
    monkeypatch.setattr(DemandCollector, "collect", fake_collect)

    pipeline = RunPipeline(settings=test_settings, session=session)
    await pipeline.execute(run.id)

    session.refresh(run)
    assert run.status == RunStatus.completed

    probes = session.exec(select(QueryProbe).where(QueryProbe.run_id == run.id)).all()
    assert len(probes) == 8


async def test_pipeline_missing_entity_fails_run(session, test_settings):
    run = Run(entity_id=999999, status=RunStatus.pending)
    session.add(run)
    session.commit()
    session.refresh(run)

    pipeline = RunPipeline(settings=test_settings, session=session)
    await pipeline.execute(run.id)

    session.refresh(run)
    assert run.status == RunStatus.failed
    assert "999999" in run.error_message


# ---------------------------------------------------------------------------
# Social signal collection -> DataPoint rows
# ---------------------------------------------------------------------------


async def test_pipeline_writes_social_datapoints(
    session, test_settings, monkeypatch, make_entity, make_run, make_probe_result,
    make_demand_result, make_extracted_entity,
):
    from provenance.collectors.social import SocialSignalResult

    entity = make_entity(name="Acme", category="graph database")
    run = make_run(entity.id)
    own = make_extracted_entity(name="Acme", recommendation_rank=1, mention_type="primary")

    async def fake_probe(self, query, query_variant, entity_name, context, competitors=None):
        return make_probe_result(
            query_variant=query_variant,
            raw_response=f"{entity_name} is great.",
            extracted_entities=[own],
        )

    def fake_demand_collect(self, entity_name, category):
        return make_demand_result(entity_name=entity_name)

    def fake_social_collect(self, entity_name):
        return [
            SocialSignalResult(signal_key="hn_story_count", signal_value=3.0),
            SocialSignalResult(signal_key="hn_points_total", signal_value=160.0),
            SocialSignalResult(
                signal_key="hn_top_story_title", signal_value=0.0, signal_text="Acme launches"
            ),
        ]

    monkeypatch.setattr(AnthropicProbe, "probe", fake_probe)
    monkeypatch.setattr(DemandCollector, "collect", fake_demand_collect)
    monkeypatch.setattr(SocialCollector, "collect", fake_social_collect)

    pipeline = RunPipeline(settings=test_settings, session=session)
    await pipeline.execute(run.id)

    session.refresh(run)
    assert run.status == RunStatus.completed

    data_points = session.exec(select(DataPoint).where(DataPoint.run_id == run.id)).all()
    assert len(data_points) == 3
    for dp in data_points:
        assert dp.run_id == run.id
        assert dp.entry_id is None
        assert dp.signal_family == "social"
        assert dp.collector_name == "social"
    by_key = {dp.signal_key: dp for dp in data_points}
    assert by_key["hn_story_count"].signal_value == 3.0
    assert by_key["hn_top_story_title"].signal_text == "Acme launches"


async def test_pipeline_social_error_result_writes_nothing(
    session, test_settings, monkeypatch, make_entity, make_run, make_probe_result,
    make_demand_result, make_extracted_entity,
):
    from provenance.collectors.social import SocialSignalResult

    entity = make_entity(name="Acme", category="graph database")
    run = make_run(entity.id)
    own = make_extracted_entity(name="Acme", recommendation_rank=1, mention_type="primary")

    async def fake_probe(self, query, query_variant, entity_name, context, competitors=None):
        return make_probe_result(
            query_variant=query_variant,
            raw_response=f"{entity_name} is great.",
            extracted_entities=[own],
        )

    def fake_demand_collect(self, entity_name, category):
        return make_demand_result(entity_name=entity_name)

    def fake_social_collect(self, entity_name):
        return [SocialSignalResult(signal_key="hn_error", signal_value=0.0, error="boom")]

    monkeypatch.setattr(AnthropicProbe, "probe", fake_probe)
    monkeypatch.setattr(DemandCollector, "collect", fake_demand_collect)
    monkeypatch.setattr(SocialCollector, "collect", fake_social_collect)

    pipeline = RunPipeline(settings=test_settings, session=session)
    await pipeline.execute(run.id)

    session.refresh(run)
    assert run.status == RunStatus.completed

    data_points = session.exec(select(DataPoint).where(DataPoint.run_id == run.id)).all()
    assert data_points == []


async def test_pipeline_social_collector_raising_still_completes(
    session, test_settings, monkeypatch, make_entity, make_run, make_probe_result,
    make_demand_result, make_extracted_entity,
):
    entity = make_entity(name="Acme", category="graph database")
    run = make_run(entity.id)
    own = make_extracted_entity(name="Acme", recommendation_rank=1, mention_type="primary")

    async def fake_probe(self, query, query_variant, entity_name, context, competitors=None):
        return make_probe_result(
            query_variant=query_variant,
            raw_response=f"{entity_name} is great.",
            extracted_entities=[own],
        )

    def fake_demand_collect(self, entity_name, category):
        return make_demand_result(entity_name=entity_name)

    def fake_social_collect_raises(self, entity_name):
        raise RuntimeError("registry blew up")

    monkeypatch.setattr(AnthropicProbe, "probe", fake_probe)
    monkeypatch.setattr(DemandCollector, "collect", fake_demand_collect)
    monkeypatch.setattr(SocialCollector, "collect", fake_social_collect_raises)

    pipeline = RunPipeline(settings=test_settings, session=session)
    await pipeline.execute(run.id)

    session.refresh(run)
    assert run.status == RunStatus.completed

    data_points = session.exec(select(DataPoint).where(DataPoint.run_id == run.id)).all()
    assert data_points == []
