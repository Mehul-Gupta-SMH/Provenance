"""Shared pytest fixtures (PLAN.md section 14).

In-memory SQLite engine/session, a TestClient wired to that same session via
dependency override, and canned ProbeResult/DemandResult factories so probe and
collector behavior can be exercised without any network access or API keys.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable, List, Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import provenance.models  # noqa: F401 — registers all SQLModel metadata
from provenance.collectors.base import DemandResult
from provenance.config import Settings
from provenance.models.database import get_session
from provenance.models.entity import Entity
from provenance.models.run import Run, RunMode, RunStatus
from provenance.probes.base import ExtractedEntity, ProbeResult


@pytest.fixture(name="engine")
def engine_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)


@pytest.fixture(name="session")
def session_fixture(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture(name="test_settings")
def test_settings_fixture() -> Settings:
    """Fast, network-free settings: dummy API key, minimal retries/delays."""
    return Settings(
        anthropic_api_key="test-key",
        anthropic_default_model="claude-test-model",
        openai_default_model="gpt-test-model",
        gemini_default_model="gemini-test-model",
        probe_max_retries=1,
        probe_timeout_seconds=5,
        pytrends_request_delay_seconds=0.0,
    )


@pytest.fixture(name="client")
def client_fixture(session):
    from main import app

    def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Canned result factories (probes / collectors)
# ---------------------------------------------------------------------------


@pytest.fixture(name="make_extracted_entity")
def make_extracted_entity_factory() -> Callable[..., ExtractedEntity]:
    def _make(
        name: str = "Acme",
        recommendation_rank: Optional[int] = 1,
        mention_type: str = "primary",
        phrasing_sentiment: Optional[str] = "positive",
        context_of_mention: Optional[str] = "recommended as the top choice",
        co_mentioned_entities: Optional[List[str]] = None,
    ) -> ExtractedEntity:
        return ExtractedEntity(
            name=name,
            recommendation_rank=recommendation_rank,
            mention_type=mention_type,
            phrasing_sentiment=phrasing_sentiment,
            context_of_mention=context_of_mention,
            co_mentioned_entities=co_mentioned_entities or [],
        )

    return _make


@pytest.fixture(name="make_probe_result")
def make_probe_result_factory(make_extracted_entity) -> Callable[..., ProbeResult]:
    def _make(
        provider: str = "anthropic",
        model: str = "claude-test-model",
        query_text: str = "What is the best graph database?",
        query_variant: str = "direct",
        raw_response: str = "Acme is a great graph database. See https://acme.example.com/docs.",
        extracted_entities: Optional[List[ExtractedEntity]] = None,
        cited_urls: Optional[List[str]] = None,
        error: Optional[str] = None,
    ) -> ProbeResult:
        return ProbeResult(
            provider=provider,
            model=model,
            query_text=query_text,
            query_variant=query_variant,
            raw_response=raw_response,
            extracted_entities=(
                extracted_entities
                if extracted_entities is not None
                else [make_extracted_entity()]
            ),
            cited_urls=cited_urls or [],
            probed_at=datetime.utcnow(),
            error=error,
        )

    return _make


@pytest.fixture(name="make_demand_result")
def make_demand_result_factory() -> Callable[..., DemandResult]:
    def _make(
        entity_name: str = "Acme",
        search_volume: Optional[float] = 42.0,
        trend_velocity: Optional[float] = 5.0,
        related_queries: Optional[List[str]] = None,
        geographic_distribution: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> DemandResult:
        return DemandResult(
            entity_name=entity_name,
            search_volume=search_volume,
            trend_velocity=trend_velocity,
            related_queries=related_queries if related_queries is not None else ["acme guide"],
            geographic_distribution=(
                geographic_distribution if geographic_distribution is not None else {"US": 90.0}
            ),
            error=error,
        )

    return _make


# ---------------------------------------------------------------------------
# DB seed helpers
# ---------------------------------------------------------------------------


@pytest.fixture(name="make_entity")
def make_entity_factory(session: Session) -> Callable[..., Entity]:
    def _make(
        name: str = "Acme",
        category: str = "graph database",
        competitors: Optional[List[str]] = None,
        query_seeds: Optional[List[str]] = None,
    ) -> Entity:
        import json

        entity = Entity(
            name=name,
            category=category,
            competitors_json=json.dumps(competitors or []),
            query_seeds_json=json.dumps(query_seeds or []),
        )
        session.add(entity)
        session.commit()
        session.refresh(entity)
        return entity

    return _make


@pytest.fixture(name="make_run")
def make_run_factory(session: Session) -> Callable[..., Run]:
    def _make(
        entity_id: int,
        status: RunStatus = RunStatus.pending,
        mode: RunMode = RunMode.isolation,
    ) -> Run:
        run = Run(entity_id=entity_id, status=status, mode=mode)
        session.add(run)
        session.commit()
        session.refresh(run)
        return run

    return _make


@pytest.fixture(name="seed_completed_run")
def seed_completed_run_factory(session: Session) -> Callable[..., Run]:
    """Seed a completed Run with QueryProbe/LLMSignal rows (one per entry in
    ``ranks_and_types``), a DemandSignal, and (by default) a real
    DivergenceEngine-computed DivergenceScore — for analysis-layer tests that
    need a fully-populated run to build fingerprints from."""

    def _seed(
        entity_id: int,
        ranks_and_types: List[tuple],
        search_volume: Optional[float] = 50.0,
        trend_velocity: Optional[float] = 2.0,
        related_queries: Optional[List[str]] = None,
        geographic_distribution: Optional[dict] = None,
        compute_divergence: bool = True,
    ) -> Run:
        import json as _json

        from provenance.core.divergence import DivergenceEngine
        from provenance.models.demand_signal import DemandSignal
        from provenance.models.llm_signal import LLMSignal
        from provenance.models.query_probe import QueryProbe

        run = Run(entity_id=entity_id, status=RunStatus.completed)
        session.add(run)
        session.commit()
        session.refresh(run)

        variants = ["direct", "comparative", "expert", "contrarian"]
        for i, (rank, mention_type, sentiment, co_mentioned) in enumerate(ranks_and_types):
            variant = variants[i % len(variants)]
            qp = QueryProbe(run_id=run.id, query_variant=variant, query_text=f"q-{variant}")
            session.add(qp)
            session.flush()
            session.add(
                LLMSignal(
                    entry_id=qp.id,
                    recommendation_rank=rank,
                    mention_type=mention_type,
                    phrasing_sentiment=sentiment,
                    co_mentioned_entities_json=_json.dumps(co_mentioned or []),
                )
            )
        session.commit()

        session.add(
            DemandSignal(
                run_id=run.id,
                search_volume=search_volume,
                trend_velocity=trend_velocity,
                related_queries_json=_json.dumps(related_queries or []),
                geographic_distribution_json=_json.dumps(geographic_distribution or {}),
            )
        )
        session.commit()

        if compute_divergence:
            DivergenceEngine(session).compute_for_run(run.id)

        return run

    return _seed
