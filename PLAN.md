I have read all the existing project artifacts. Now I will produce the comprehensive implementation plan.

---

# Provenance â€” Comprehensive Implementation Plan

**Version:** 1.0  
**Date:** 2026-03-15  
**Status:** Planning artifact â€” source of truth for v1 implementation

---

## Table of Contents

1. [Phase Overview](#1-phase-overview)
2. [Dependency Order](#2-dependency-order)
3. [Low-Level Design: Configuration and Bootstrapping](#3-low-level-design-configuration-and-bootstrapping)
4. [Low-Level Design: Database Models](#4-low-level-design-database-models)
5. [Low-Level Design: Registry Pattern](#5-low-level-design-registry-pattern)
6. [Low-Level Design: Abstract Bases](#6-low-level-design-abstract-bases)
7. [Low-Level Design: Probes](#7-low-level-design-probes)
8. [Low-Level Design: Collectors](#8-low-level-design-collectors)
9. [Low-Level Design: Pipeline Orchestration](#9-low-level-design-pipeline-orchestration)
10. [Low-Level Design: Divergence Engine](#10-low-level-design-divergence-engine)
11. [Low-Level Design: Competitor Delta and Gap Analysis](#11-low-level-design-competitor-delta-and-gap-analysis)
12. [Low-Level Design: API Layer](#12-low-level-design-api-layer)
13. [Alembic Migration Strategy](#13-alembic-migration-strategy)
14. [Test Strategy](#14-test-strategy)
15. [Risk Areas](#15-risk-areas)

---

## 1. Phase Overview

### Phase 0 â€” Foundation (Prerequisite for everything)

Deliverables at boundary:
- `config.py` with all settings loaded from environment
- `main.py` with FastAPI app instantiated, `/health` route live
- All SQLModel table definitions in `models/`
- Alembic initialized, initial migration generated and applied
- Empty registry and abstract base classes committed

Nothing is callable at the API level except `/health`. No probes, no pipeline, no routes beyond health.

Boundary check: `alembic upgrade head` runs clean. SQLite file is created. All tables exist.

---

### Phase 1 â€” Entity CRUD

Deliverables at boundary:
- `models/entity.py` complete with all columns
- `api/v1/routes/entities.py` with full CRUD (POST, GET, GET list, PATCH, DELETE)
- Service layer function for each operation
- Alembic migration for entity table

Boundary check: Full round-trip via `curl` or a test client. Create entity, retrieve it, update it, delete it.

---

### Phase 2 â€” Run Lifecycle (no execution yet)

Deliverables at boundary:
- `models/run.py` complete
- `api/v1/routes/runs.py` with POST (create run), GET (fetch run status), GET list by entity
- Run status enum: `pending | running | completed | failed`
- Service layer creates run record and returns run_id

Boundary check: POST to `/v1/runs` returns a run record with `status=pending`. GET retrieves it.

---

### Phase 3 â€” Probe Infrastructure

Deliverables at boundary:
- `probes/base.py` â€” `BaseProbe` ABC with full interface
- `probes/anthropic.py` â€” `AnthropicProbe` functional implementation
- `probes/openai.py` â€” `OpenAIProbe` stub that returns a canned response conforming to the interface
- `probes/gemini.py` â€” `GeminiProbe` stub same as above
- `core/registry.py` â€” `ProbeRegistry` with register/get/list
- All three probes registered on application startup

Boundary check: In isolation (no API), instantiate `AnthropicProbe`, call `probe()` with a test query, receive a `ProbeResult` dataclass back.

---

### Phase 4 â€” Collector Infrastructure

Deliverables at boundary:
- `collectors/base.py` â€” `BaseCollector` ABC
- `collectors/demand.py` â€” `DemandCollector` functional (pytrends)
- `collectors/citation.py` â€” `CitationExtractor` functional (regex/URL parsing from LLM response text)
- `CollectorRegistry` registered in `core/registry.py`

Boundary check: In isolation, instantiate `DemandCollector`, call `collect("neo4j", "graph database")`, receive a `DemandResult` back. Instantiate `CitationExtractor`, pass a raw LLM response string with URLs, receive `List[CitationResult]`.

---

### Phase 5 â€” Pipeline Execution

Deliverables at boundary:
- `core/pipeline.py` â€” `RunPipeline` orchestrator
- FastAPI background task wired to `POST /v1/runs` â€” fires pipeline after creating run record
- `models/query_probe.py`, `models/llm_signal.py`, `models/demand_signal.py`, `models/citation.py` all written during pipeline execution
- Run status transitions: `pending â†’ running â†’ completed | failed`

Boundary check: POST a run for an entity with a valid Anthropic key. Wait (poll GET run). Status reaches `completed`. Database contains QueryProbe, LLMSignal, DemandSignal, and Citation rows for the run.

---

### Phase 6 â€” Divergence Engine

Deliverables at boundary:
- `core/divergence.py` â€” `DivergenceEngine` with computation logic
- `models/divergence_score.py` â€” DivergenceScore table
- `POST /v1/runs/{run_id}/divergence` â€” triggers computation (or auto-triggered at pipeline completion)
- `GET /v1/runs/{run_id}/divergence` â€” returns computed scores

Boundary check: After a completed run, call divergence endpoint. Receive DivergenceScore rows with `demand_llm_alignment_score`, `divergence_direction`, `cross_query_stability`.

---

### Phase 7 â€” Analysis Layer (Competitor Delta + Gap Analysis)

Deliverables at boundary:
- `core/analysis.py` â€” `FingerprintBuilder`, `CompetitorDelta`, `GapAnalyzer`
- `GET /v1/entities/{entity_id}/fingerprint` â€” returns assembled fingerprint for latest or specified run
- `POST /v1/analysis/competitor-delta` â€” accepts two entity_ids, returns diff
- `POST /v1/analysis/gap` â€” accepts entity_id + competitor_entity_id (or ideal target), returns prioritized gap list

Boundary check: With two entities that each have completed runs, call `/v1/analysis/competitor-delta`. Receive a structured diff of signal vectors. Call `/v1/analysis/gap`. Receive a list of gaps ordered by estimated impact score.

---

### Phase 8 â€” Hardening

Deliverables at boundary:
- Full test suite passing (unit + integration)
- Error handling on all routes (HTTP exceptions with structured error body)
- pytrends rate-limit handling with backoff
- Anthropic rate-limit / timeout handling with retry
- Logging throughout pipeline (structured JSON)
- `README.md` updated with full API reference

---

## 2. Dependency Order

```
config.py
    |
models/ (all tables)
    |
alembic init + initial migration
    |
    +-- probes/base.py          collectors/base.py
    |        |                           |
    |   probes/anthropic.py     collectors/demand.py
    |   probes/openai.py        collectors/citation.py
    |   probes/gemini.py
    |
core/registry.py  (depends on bases, registers all probes + collectors)
    |
api/v1/routes/entities.py  (depends on models, no registry dependency)
    |
api/v1/routes/runs.py  (depends on models + registry)
    |
core/pipeline.py  (depends on registry, models, all probes, all collectors)
    |
core/divergence.py  (depends on models: QueryProbe, LLMSignal, DemandSignal)
    |
core/analysis.py  (depends on divergence.py, models)
    |
api/v1/routes/analysis.py  (depends on core/analysis.py)
```

---

## 3. Low-Level Design: Configuration and Bootstrapping

### `/provenance/config.py`

```python
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite:///./provenance.db"

    # Anthropic
    anthropic_api_key: str
    anthropic_default_model: str = "claude-opus-4-5"
    anthropic_default_temperature: float = 0.2

    # OpenAI (stubbed)
    openai_api_key: str = ""
    openai_default_model: str = "gpt-4o"

    # Gemini (stubbed)
    gemini_api_key: str = ""
    gemini_default_model: str = "gemini-1.5-pro"

    # Probing defaults
    default_probe_mode: str = "isolation"  # "isolation" | "aggregate"
    probe_timeout_seconds: int = 60
    probe_max_retries: int = 3

    # pytrends
    pytrends_request_delay_seconds: float = 1.0
    pytrends_timeout: int = 30

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

@lru_cache()
def get_settings() -> Settings:
    return Settings()
```

### `/provenance/main.py`

```python
from fastapi import FastAPI
from provenance.core.registry import ProbeRegistry, CollectorRegistry
from provenance.probes.anthropic import AnthropicProbe
from provenance.probes.openai import OpenAIProbe
from provenance.probes.gemini import GeminiProbe
from provenance.collectors.demand import DemandCollector
from provenance.collectors.citation import CitationExtractor
from provenance.api.v1.routes import entities, runs, signals, analysis
from provenance.models.database import create_db_and_tables

app = FastAPI(title="Provenance", version="1.0.0")

@app.on_event("startup")
def on_startup():
    create_db_and_tables()
    ProbeRegistry.register("anthropic", AnthropicProbe)
    ProbeRegistry.register("openai", OpenAIProbe)
    ProbeRegistry.register("gemini", GeminiProbe)
    CollectorRegistry.register("demand", DemandCollector)
    CollectorRegistry.register("citation", CitationExtractor)

app.include_router(entities.router, prefix="/v1")
app.include_router(runs.router, prefix="/v1")
app.include_router(signals.router, prefix="/v1")
app.include_router(analysis.router, prefix="/v1")

@app.get("/health")
def health():
    return {"status": "ok"}
```

### `/provenance/models/database.py`

```python
from sqlmodel import SQLModel, create_engine, Session
from provenance.config import get_settings
from typing import Generator

settings = get_settings()
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False}  # SQLite only
)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
```

Note: `create_db_and_tables()` is called only for local dev / testing. In production, Alembic controls schema. The startup call is a safety net and is idempotent.

---

## 4. Low-Level Design: Database Models

All models live in `provenance/models/`. Every SQLModel table class has both `table=True` (SQLAlchemy) and a companion Pydantic schema (separate `Read`/`Create` classes).

### `models/entity.py`

```python
from sqlmodel import SQLModel, Field
from typing import Optional, List
from datetime import datetime
import json

class EntityBase(SQLModel):
    name: str = Field(index=True)
    category: str
    url: Optional[str] = None
    # Stored as JSON string; deserialized at service layer
    competitors_json: str = Field(default="[]", sa_column_kwargs={"name": "competitors"})
    query_seeds_json: str = Field(default="[]", sa_column_kwargs={"name": "query_seeds"})

class Entity(EntityBase, table=True):
    __tablename__ = "entity"
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class EntityCreate(SQLModel):
    name: str
    category: str
    url: Optional[str] = None
    competitors: List[str] = []
    query_seeds: List[str] = []

class EntityRead(SQLModel):
    id: int
    name: str
    category: str
    url: Optional[str]
    competitors: List[str]
    query_seeds: List[str]
    created_at: datetime
    updated_at: datetime

class EntityUpdate(SQLModel):
    name: Optional[str] = None
    category: Optional[str] = None
    url: Optional[str] = None
    competitors: Optional[List[str]] = None
    query_seeds: Optional[List[str]] = None
```

Design note: Lists (competitors, query_seeds) are stored as JSON strings in SQLite. The service layer serializes/deserializes. This avoids a junction table, keeps the schema flat, and is Postgres-compatible (can migrate to JSONB column type via Alembic with no data loss).

---

### `models/run.py`

```python
from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum

class RunStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"

class RunMode(str, Enum):
    isolation = "isolation"
    aggregate = "aggregate"

class RunBase(SQLModel):
    entity_id: int = Field(foreign_key="entity.id", index=True)
    mode: RunMode = RunMode.isolation
    status: RunStatus = RunStatus.pending

class Run(RunBase, table=True):
    __tablename__ = "run"
    id: Optional[int] = Field(default=None, primary_key=True)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class RunCreate(SQLModel):
    entity_id: int
    mode: RunMode = RunMode.isolation

class RunRead(SQLModel):
    id: int
    entity_id: int
    mode: RunMode
    status: RunStatus
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    created_at: datetime
```

---

### `models/query_probe.py`

This is the widest table in the system. All ProbeContext fields are flat columns â€” no nesting, no JSON blobs. This is the core architectural decision from the thesis ("flat schema, late derivation").

```python
from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

class QueryProbe(SQLModel, table=True):
    __tablename__ = "query_probe"
    id: Optional[int] = Field(default=None, primary_key=True)

    # Run linkage
    run_id: int = Field(foreign_key="run.id", index=True)

    # Query context
    query_variant: str          # "direct" | "comparative" | "expert" | "contrarian"
    query_text: str             # the actual query string sent

    # Raw LLM response
    raw_response: str           # full text response from LLM

    # Temporal context (flat, no bucketing)
    probed_at: datetime = Field(default_factory=datetime.utcnow)

    # Geographic context
    country: str = "US"
    region: Optional[str] = None
    language: str = "en"
    locale: str = "en-US"

    # User context
    user_persona: Optional[str] = None     # e.g. "developer", "enterprise_buyer"
    expertise_level: Optional[str] = None  # "beginner" | "intermediate" | "expert"
    stated_use_case: Optional[str] = None  # e.g. "production", "prototyping"

    # LLM context
    provider: str               # "anthropic" | "openai" | "gemini"
    model: str                  # exact model string, e.g. "claude-opus-4-5"
    temperature: float
    system_prompt_variant: Optional[str] = None  # label for system prompt used
    prior_context: Optional[str] = None           # JSON string of conversation history
```

---

### `models/llm_signal.py`

```python
from sqlmodel import SQLModel, Field
from typing import Optional

class LLMSignal(SQLModel, table=True):
    __tablename__ = "llm_signal"
    id: Optional[int] = Field(default=None, primary_key=True)

    probe_id: int = Field(foreign_key="query_probe.id", index=True)
    entity_id: int = Field(foreign_key="entity.id", index=True)

    # Recommendation signals
    recommendation_rank: Optional[int] = None   # 1, 2, 3... or None if absent
    mention_type: str = "absent"                 # "primary" | "alternative" | "cautionary" | "absent"
    phrasing_sentiment: Optional[str] = None    # "positive" | "neutral" | "qualified"
    context_of_mention: Optional[str] = None    # free text: use-case or constraint satisfied

    # Co-mention signals
    co_mentioned_entities_json: str = Field(default="[]")  # JSON list of entity names

    # Stability signals (derived, stored here for query convenience)
    query_sensitivity: Optional[float] = None  # 0-1: how much rank varies across variants
```

---

### `models/demand_signal.py`

```python
from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

class DemandSignal(SQLModel, table=True):
    __tablename__ = "demand_signal"
    id: Optional[int] = Field(default=None, primary_key=True)

    entity_id: int = Field(foreign_key="entity.id", index=True)
    run_id: int = Field(foreign_key="run.id", index=True)
    collected_at: datetime = Field(default_factory=datetime.utcnow)

    # Raw demand signals (all flat columns)
    search_volume: Optional[float] = None          # 0-100 (pytrends relative)
    trend_velocity: Optional[float] = None         # 30-day delta, signed float
    related_queries_json: str = Field(default="[]")    # JSON: top 5 rising related queries
    geographic_distribution_json: str = Field(default="{}")  # JSON: {region: score}
```

---

### `models/citation.py`

```python
from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

class Citation(SQLModel, table=True):
    __tablename__ = "citation"
    id: Optional[int] = Field(default=None, primary_key=True)

    probe_id: int = Field(foreign_key="query_probe.id", index=True)

    cited_url: str
    domain: str                                 # extracted from cited_url
    page_recency: Optional[datetime] = None    # from page meta if available
    content_type: Optional[str] = None         # "docs" | "blog" | "comparison" | "review" | "forum"
    entity_mention_count: Optional[int] = None  # how often entity appears on cited page
```

---

### `models/divergence_score.py`

This is a derived/cached table. It is never a source of truth. It is computed at the end of a run and can be recomputed at any time from the raw probe data.

```python
from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

class DivergenceScore(SQLModel, table=True):
    __tablename__ = "divergence_score"
    id: Optional[int] = Field(default=None, primary_key=True)

    run_id: int = Field(foreign_key="run.id", index=True)
    entity_id: int = Field(foreign_key="entity.id", index=True)
    computed_at: datetime = Field(default_factory=datetime.utcnow)

    # Core divergence signals
    demand_llm_alignment_score: float          # 0.0 to 1.0
    divergence_direction: str                  # "llm_ahead" | "demand_ahead" | "aligned"
    cross_query_stability: float               # 0.0 to 1.0

    # Supporting detail
    average_recommendation_rank: Optional[float] = None
    mention_type_distribution_json: str = Field(default="{}")  # JSON: {type: count}
    probes_included: int = 0                   # how many probes factored in
```

---

## 5. Low-Level Design: Registry Pattern

### `core/registry.py`

The registry is a simple class-level dictionary. Instances are created by the caller, not by the registry. The registry holds class references, not instances.

```python
from typing import Type, Dict, TypeVar
from provenance.probes.base import BaseProbe
from provenance.collectors.base import BaseCollector

T = TypeVar("T")

class _Registry:
    """Generic class registry. Holds class references keyed by string names."""

    def __init__(self, base_class: type):
        self._base_class = base_class
        self._registry: Dict[str, type] = {}

    def register(self, name: str, cls: type) -> None:
        if not issubclass(cls, self._base_class):
            raise TypeError(f"{cls} must be a subclass of {self._base_class}")
        self._registry[name] = cls

    def get(self, name: str) -> type:
        if name not in self._registry:
            raise KeyError(f"No registered implementation for '{name}'. "
                           f"Available: {list(self._registry.keys())}")
        return self._registry[name]

    def list(self) -> list[str]:
        return list(self._registry.keys())

    def all(self) -> Dict[str, type]:
        return dict(self._registry)


ProbeRegistry = _Registry(BaseProbe)
CollectorRegistry = _Registry(BaseCollector)
```

Usage pattern in the pipeline:

```python
probe_cls = ProbeRegistry.get("anthropic")
probe = probe_cls(settings=get_settings())
result = await probe.probe(query="...", context=probe_context)
```

---

## 6. Low-Level Design: Abstract Bases

### `probes/base.py`

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime

@dataclass
class ProbeContext:
    """All context parameters for a single LLM probe call."""
    country: str = "US"
    region: Optional[str] = None
    language: str = "en"
    locale: str = "en-US"
    user_persona: Optional[str] = None
    expertise_level: Optional[str] = None
    stated_use_case: Optional[str] = None
    temperature: float = 0.2
    system_prompt_variant: Optional[str] = None
    prior_context: Optional[str] = None  # JSON string

@dataclass
class ExtractedEntity:
    """Single entity extraction result from a probe response."""
    name: str
    recommendation_rank: Optional[int]
    mention_type: str         # "primary" | "alternative" | "cautionary" | "absent"
    phrasing_sentiment: Optional[str]
    context_of_mention: Optional[str]
    co_mentioned_entities: List[str] = field(default_factory=list)

@dataclass
class ProbeResult:
    """The normalized output of a single LLM probe call."""
    provider: str
    model: str
    query_text: str
    query_variant: str
    raw_response: str
    extracted_entities: List[ExtractedEntity]
    cited_urls: List[str]          # raw URL strings found in response
    probed_at: datetime = field(default_factory=datetime.utcnow)
    error: Optional[str] = None    # set if probe failed non-fatally

class BaseProbe(ABC):
    """Abstract base for all LLM probe implementations."""

    provider_name: str  # class-level constant, e.g. "anthropic"

    def __init__(self, settings):
        self.settings = settings

    @abstractmethod
    async def probe(
        self,
        query: str,
        query_variant: str,
        entity_name: str,
        context: ProbeContext,
    ) -> ProbeResult:
        """
        Execute a single LLM probe.
        Must return a ProbeResult even on soft failures (set error field).
        Raise only on unrecoverable errors.
        """
        ...

    @abstractmethod
    def _build_prompt(
        self,
        query: str,
        entity_name: str,
        context: ProbeContext,
    ) -> str:
        """Build the full prompt string for this probe."""
        ...

    @abstractmethod
    def _extract_entities(
        self,
        raw_response: str,
        entity_name: str,
        competitors: List[str],
    ) -> List[ExtractedEntity]:
        """
        Parse the raw LLM response into structured ExtractedEntity objects.
        This is the signal extraction step.
        """
        ...

    def _extract_urls(self, raw_response: str) -> List[str]:
        """
        Default URL extraction via regex.
        Probes may override if the provider returns structured citations.
        """
        import re
        url_pattern = r'https?://[^\s\)\]\>"\']+' 
        return list(set(re.findall(url_pattern, raw_response)))
```

---

### `collectors/base.py`

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict

@dataclass
class DemandResult:
    entity_name: str
    search_volume: Optional[float]        # 0-100
    trend_velocity: Optional[float]       # signed delta
    related_queries: List[str] = field(default_factory=list)
    geographic_distribution: Dict[str, float] = field(default_factory=dict)
    error: Optional[str] = None

@dataclass
class CitationResult:
    cited_url: str
    domain: str
    content_type: Optional[str] = None
    entity_mention_count: Optional[int] = None
    page_recency: Optional[str] = None   # ISO datetime string if found
    error: Optional[str] = None

class BaseCollector(ABC):
    """Abstract base for all signal collectors."""

    collector_name: str  # class-level constant

    def __init__(self, settings):
        self.settings = settings

    @abstractmethod
    def collect(self, *args, **kwargs):
        """Execute collection. Return type varies by collector subclass."""
        ...
```

---

## 7. Low-Level Design: Probes

### `probes/anthropic.py`

The Anthropic probe is the only functional probe in v1. Its entity extraction uses a structured second LLM call (extraction pass) rather than regex â€” this produces cleaner signal and is more robust to varied response formats.

```python
import anthropic
import json
import asyncio
from typing import List, Optional
from provenance.probes.base import BaseProbe, ProbeContext, ProbeResult, ExtractedEntity
from provenance.config import Settings

EXTRACTION_SYSTEM_PROMPT = """
You are a structured data extractor. Given an LLM recommendation response and a list of entities,
extract exactly what was said about each entity. Return JSON only, no prose.

Output schema:
{
  "entities": [
    {
      "name": "string",
      "recommendation_rank": null | integer (1 = mentioned first/primary),
      "mention_type": "primary" | "alternative" | "cautionary" | "absent",
      "phrasing_sentiment": "positive" | "neutral" | "qualified" | null,
      "context_of_mention": "string or null",
      "co_mentioned_entities": ["string", ...]
    }
  ]
}
"""

QUERY_TEMPLATES = {
    "direct":      "What is the best {category}?",
    "comparative": "Compare the top options for {category}. Which would you recommend?",
    "expert":      "As a technical expert, which {category} would you choose for a production environment?",
    "contrarian":  "What is the most underrated option for {category} that experts often miss?",
}

class AnthropicProbe(BaseProbe):
    provider_name = "anthropic"

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    async def probe(
        self,
        query: str,
        query_variant: str,
        entity_name: str,
        context: ProbeContext,
        competitors: Optional[List[str]] = None,
    ) -> ProbeResult:
        from datetime import datetime
        competitors = competitors or []

        try:
            messages = []
            if context.prior_context:
                prior = json.loads(context.prior_context)
                messages.extend(prior)
            messages.append({"role": "user", "content": query})

            system = self._build_system(context)

            # Run in thread pool (Anthropic SDK is synchronous)
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._client.messages.create(
                    model=self.settings.anthropic_default_model,
                    max_tokens=1500,
                    temperature=context.temperature,
                    system=system,
                    messages=messages,
                )
            )

            raw_response = response.content[0].text
            extracted = self._extract_entities(raw_response, entity_name, competitors)
            urls = self._extract_urls(raw_response)

            return ProbeResult(
                provider=self.provider_name,
                model=self.settings.anthropic_default_model,
                query_text=query,
                query_variant=query_variant,
                raw_response=raw_response,
                extracted_entities=extracted,
                cited_urls=urls,
                probed_at=datetime.utcnow(),
            )

        except Exception as e:
            return ProbeResult(
                provider=self.provider_name,
                model=self.settings.anthropic_default_model,
                query_text=query,
                query_variant=query_variant,
                raw_response="",
                extracted_entities=[],
                cited_urls=[],
                error=str(e),
            )

    def _build_system(self, context: ProbeContext) -> str:
        parts = ["You are a helpful assistant providing honest recommendations."]
        if context.user_persona:
            parts.append(f"You are assisting a {context.user_persona}.")
        if context.expertise_level:
            parts.append(f"The user has {context.expertise_level} expertise.")
        if context.stated_use_case:
            parts.append(f"Their use case is: {context.stated_use_case}.")
        return " ".join(parts)

    def _build_prompt(self, query: str, entity_name: str, context: ProbeContext) -> str:
        return query  # query is pre-built by pipeline; prompt is just the query

    def _extract_entities(
        self,
        raw_response: str,
        entity_name: str,
        competitors: List[str],
    ) -> List[ExtractedEntity]:
        """Use a second Anthropic call to extract structured signal."""
        all_entities = [entity_name] + competitors
        extraction_prompt = f"""
Response to analyze:
---
{raw_response}
---

Entities to extract: {json.dumps(all_entities)}

Extract the recommendation signal for each entity. Return JSON only.
"""
        try:
            resp = self._client.messages.create(
                model=self.settings.anthropic_default_model,
                max_tokens=1000,
                temperature=0.0,
                system=EXTRACTION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": extraction_prompt}],
            )
            data = json.loads(resp.content[0].text)
            results = []
            for e in data.get("entities", []):
                results.append(ExtractedEntity(
                    name=e["name"],
                    recommendation_rank=e.get("recommendation_rank"),
                    mention_type=e.get("mention_type", "absent"),
                    phrasing_sentiment=e.get("phrasing_sentiment"),
                    context_of_mention=e.get("context_of_mention"),
                    co_mentioned_entities=e.get("co_mentioned_entities", []),
                ))
            return results
        except Exception:
            # Fallback: return absent signal for all entities
            return [
                ExtractedEntity(
                    name=name,
                    recommendation_rank=None,
                    mention_type="absent",
                    phrasing_sentiment=None,
                    context_of_mention=None,
                )
                for name in all_entities
            ]
```

Design note: The extraction uses a second LLM call with `temperature=0.0`. This is deliberate â€” extraction is a deterministic parsing task, not a creative one. The cost is one additional API call per probe. This is acceptable in v1. In v2, this can be replaced with structured output (tool use / JSON mode).

---

### `probes/openai.py` and `probes/gemini.py`

Both stubs return a canned `ProbeResult` that is structurally valid but contains no real data. They log a warning.

```python
# openai.py
import logging
from datetime import datetime
from provenance.probes.base import BaseProbe, ProbeContext, ProbeResult

logger = logging.getLogger(__name__)

class OpenAIProbe(BaseProbe):
    provider_name = "openai"

    async def probe(self, query, query_variant, entity_name, context, competitors=None) -> ProbeResult:
        logger.warning("OpenAIProbe is stubbed. Returning empty result.")
        return ProbeResult(
            provider=self.provider_name,
            model=self.settings.openai_default_model,
            query_text=query,
            query_variant=query_variant,
            raw_response="[STUB: OpenAI probe not implemented in v1]",
            extracted_entities=[],
            cited_urls=[],
            probed_at=datetime.utcnow(),
            error="stub",
        )

    def _build_prompt(self, query, entity_name, context): return query
    def _extract_entities(self, raw_response, entity_name, competitors): return []
```

---

## 8. Low-Level Design: Collectors

### `collectors/demand.py`

```python
from pytrends.request import TrendReq
import time
from typing import Optional
from provenance.collectors.base import BaseCollector, DemandResult
from provenance.config import Settings

class DemandCollector(BaseCollector):
    collector_name = "demand"

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self._pytrends = TrendReq(
            hl="en-US",
            tz=360,
            timeout=(settings.pytrends_timeout, settings.pytrends_timeout),
        )

    def collect(self, entity_name: str, category: str) -> DemandResult:
        """
        Collect demand signals for entity_name using pytrends.
        Uses category as additional keyword context.
        """
        try:
            keywords = [entity_name]
            self._pytrends.build_payload(
                kw_list=keywords,
                cat=0,
                timeframe="today 1-m",
                geo="",
            )
            time.sleep(self.settings.pytrends_request_delay_seconds)

            # Interest over time
            iot_df = self._pytrends.interest_over_time()
            if iot_df.empty:
                search_volume = 0.0
                trend_velocity = 0.0
            else:
                values = iot_df[entity_name].tolist()
                search_volume = float(values[-1]) if values else 0.0
                if len(values) >= 7:
                    recent = sum(values[-7:]) / 7
                    prior = sum(values[-14:-7]) / 7
                    trend_velocity = round(recent - prior, 2)
                else:
                    trend_velocity = 0.0

            time.sleep(self.settings.pytrends_request_delay_seconds)

            # Related queries
            related = self._pytrends.related_queries()
            rising = related.get(entity_name, {}).get("rising")
            related_queries = []
            if rising is not None and not rising.empty:
                related_queries = rising["query"].head(5).tolist()

            time.sleep(self.settings.pytrends_request_delay_seconds)

            # Geographic distribution
            regional = self._pytrends.interest_by_region(resolution="COUNTRY", inc_low_vol=False)
            geo_dist = {}
            if not regional.empty:
                top_regions = regional[entity_name].sort_values(ascending=False).head(5)
                geo_dist = {str(k): float(v) for k, v in top_regions.items()}

            return DemandResult(
                entity_name=entity_name,
                search_volume=search_volume,
                trend_velocity=trend_velocity,
                related_queries=related_queries,
                geographic_distribution=geo_dist,
            )

        except Exception as e:
            return DemandResult(
                entity_name=entity_name,
                search_volume=None,
                trend_velocity=None,
                error=str(e),
            )
```

---

### `collectors/citation.py`

```python
import re
from urllib.parse import urlparse
from typing import List
from provenance.collectors.base import BaseCollector, CitationResult
from provenance.config import Settings

CONTENT_TYPE_HINTS = {
    "docs": ["docs.", "/docs/", "documentation", "reference", "api-reference"],
    "blog": ["blog.", "/blog/", "medium.com", "dev.to", "substack"],
    "comparison": ["vs", "compare", "comparison", "versus", "alternative"],
    "review": ["review", "benchmark", "test", "evaluation"],
    "forum": ["reddit.com", "stackoverflow.com", "news.ycombinator.com", "forum"],
}

class CitationExtractor(BaseCollector):
    collector_name = "citation"

    def __init__(self, settings: Settings):
        super().__init__(settings)

    def collect(self, raw_response: str, entity_name: str) -> List[CitationResult]:
        """
        Extract and classify citation URLs from a raw LLM response string.
        Does not make any HTTP requests. Pure string analysis.
        """
        url_pattern = r'https?://[^\s\)\]\>"\'<]+'
        urls = list(set(re.findall(url_pattern, raw_response)))

        results = []
        for url in urls:
            try:
                parsed = urlparse(url)
                domain = parsed.netloc.lower().replace("www.", "")
                content_type = self._infer_content_type(url)
                mention_count = self._count_entity_mentions(url, entity_name)

                results.append(CitationResult(
                    cited_url=url,
                    domain=domain,
                    content_type=content_type,
                    entity_mention_count=mention_count,
                ))
            except Exception as e:
                results.append(CitationResult(
                    cited_url=url,
                    domain="",
                    error=str(e),
                ))
        return results

    def _infer_content_type(self, url: str) -> Optional[str]:
        url_lower = url.lower()
        for ctype, hints in CONTENT_TYPE_HINTS.items():
            if any(h in url_lower for h in hints):
                return ctype
        return None

    def _count_entity_mentions(self, url: str, entity_name: str) -> int:
        """
        Count how many times entity_name appears in the URL path itself.
        Full page crawling is out of scope for v1.
        """
        return url.lower().count(entity_name.lower())
```

Design note: In v1, citation extraction is purely URL-based (no HTTP fetching). `entity_mention_count` is computed from the URL string only, not page content. This is intentionally limited. The schema supports richer values when page crawling is added in v2.

---

## 9. Low-Level Design: Pipeline Orchestration

### `core/pipeline.py`

The pipeline is the central orchestrator. It is called by the FastAPI background task. It is a pure async function â€” no FastAPI dependency injection inside it.

```python
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional
from sqlmodel import Session, select

from provenance.models.run import Run, RunStatus
from provenance.models.query_probe import QueryProbe
from provenance.models.llm_signal import LLMSignal
from provenance.models.demand_signal import DemandSignal
from provenance.models.citation import Citation
from provenance.models.entity import Entity
from provenance.probes.base import ProbeContext, QUERY_TEMPLATES
from provenance.collectors.demand import DemandCollector
from provenance.collectors.citation import CitationExtractor
from provenance.core.registry import ProbeRegistry
from provenance.core.divergence import DivergenceEngine
from provenance.config import Settings

logger = logging.getLogger(__name__)


class RunPipeline:
    """
    Orchestrates a full Provenance run for one entity.

    Step order:
    1. Mark run as running
    2. Load entity + competitors
    3. Collect demand signals for entity + all competitors
    4. Execute LLM probes (4 query variants Ã— configured providers)
    5. Write QueryProbe rows
    6. Extract + write LLMSignal rows
    7. Extract + write Citation rows
    8. Compute + write DivergenceScore
    9. Mark run as completed (or failed)
    """

    def __init__(self, settings: Settings, session: Session):
        self.settings = settings
        self.session = session

    async def execute(self, run_id: int) -> None:
        run = self.session.get(Run, run_id)
        if not run:
            logger.error(f"Run {run_id} not found")
            return

        entity = self.session.get(Entity, run.entity_id)
        if not entity:
            self._fail_run(run, "Entity not found")
            return

        run.status = RunStatus.running
        run.started_at = datetime.utcnow()
        self.session.add(run)
        self.session.commit()

        try:
            competitors = json.loads(entity.competitors_json)

            # Step 3: Demand signals
            await self._collect_demand_signals(entity, competitors, run)

            # Step 4-7: LLM probes
            providers = self._resolve_providers(run.mode)
            for provider_name in providers:
                await self._execute_provider_probes(
                    run, entity, competitors, provider_name
                )

            # Step 8: Divergence
            engine = DivergenceEngine(self.session)
            engine.compute_and_store(run_id=run.id, entity_id=entity.id)

            # Step 9: Mark complete
            run.status = RunStatus.completed
            run.completed_at = datetime.utcnow()
            self.session.add(run)
            self.session.commit()

        except Exception as e:
            logger.exception(f"Pipeline failed for run {run_id}")
            self._fail_run(run, str(e))

    def _resolve_providers(self, mode) -> list[str]:
        from provenance.models.run import RunMode
        if mode == RunMode.isolation:
            return ["anthropic"]
        else:
            return ProbeRegistry.list()

    async def _collect_demand_signals(self, entity, competitors, run) -> None:
        collector = DemandCollector(self.settings)
        all_names = [entity.name] + json.loads(entity.competitors_json)

        for name in all_names:
            result = collector.collect(name, entity.category)
            signal = DemandSignal(
                entity_id=entity.id,
                run_id=run.id,
                search_volume=result.search_volume,
                trend_velocity=result.trend_velocity,
                related_queries_json=json.dumps(result.related_queries),
                geographic_distribution_json=json.dumps(result.geographic_distribution),
            )
            self.session.add(signal)
        self.session.commit()

    async def _execute_provider_probes(self, run, entity, competitors, provider_name) -> None:
        probe_cls = ProbeRegistry.get(provider_name)
        probe = probe_cls(self.settings)
        context = self._build_probe_context()
        query_seeds = json.loads(entity.query_seeds_json)

        for variant, template in QUERY_TEMPLATES.items():
            query = template.format(category=entity.category)

            result = await probe.probe(
                query=query,
                query_variant=variant,
                entity_name=entity.name,
                context=context,
                competitors=competitors,
            )

            # Write QueryProbe
            qp = QueryProbe(
                run_id=run.id,
                query_variant=variant,
                query_text=query,
                raw_response=result.raw_response,
                probed_at=result.probed_at,
                country=context.country,
                language=context.language,
                locale=context.locale,
                user_persona=context.user_persona,
                expertise_level=context.expertise_level,
                stated_use_case=context.stated_use_case,
                provider=result.provider,
                model=result.model,
                temperature=context.temperature,
                system_prompt_variant=context.system_prompt_variant,
                prior_context=context.prior_context,
            )
            self.session.add(qp)
            self.session.flush()  # get qp.id

            # Write LLMSignal per entity
            all_entity_names = [entity.name] + competitors
            for extracted in result.extracted_entities:
                target_entity_id = self._resolve_entity_id(extracted.name, entity, all_entity_names)
                if target_entity_id is None:
                    continue
                signal = LLMSignal(
                    probe_id=qp.id,
                    entity_id=target_entity_id,
                    recommendation_rank=extracted.recommendation_rank,
                    mention_type=extracted.mention_type,
                    phrasing_sentiment=extracted.phrasing_sentiment,
                    context_of_mention=extracted.context_of_mention,
                    co_mentioned_entities_json=json.dumps(extracted.co_mentioned_entities),
                )
                self.session.add(signal)

            # Write Citations
            citation_extractor = CitationExtractor(self.settings)
            citations = citation_extractor.collect(result.raw_response, entity.name)
            for c in citations:
                cit = Citation(
                    probe_id=qp.id,
                    cited_url=c.cited_url,
                    domain=c.domain,
                    content_type=c.content_type,
                    entity_mention_count=c.entity_mention_count,
                )
                self.session.add(cit)

            self.session.commit()

    def _build_probe_context(self) -> ProbeContext:
        """Build default probe context from settings. Extensible for future persona/geo runs."""
        return ProbeContext(
            temperature=self.settings.anthropic_default_temperature,
        )

    def _resolve_entity_id(self, name: str, primary_entity, all_names: list) -> Optional[int]:
        """
        For LLMSignal, we need the entity_id. For the primary entity, we have it.
        For competitors, they may not exist as Entity rows. In v1, only the primary entity_id is stored.
        Competitors are captured in co_mentioned_entities_json on the primary signal.
        """
        if name.lower() == primary_entity.name.lower():
            return primary_entity.id
        # Competitors not tracked as separate entities unless they have their own Entity rows
        result = self.session.exec(
            select(Entity).where(Entity.name == name)
        ).first()
        return result.id if result else None

    def _fail_run(self, run: Run, error: str) -> None:
        run.status = RunStatus.failed
        run.completed_at = datetime.utcnow()
        run.error_message = error
        self.session.add(run)
        self.session.commit()
```

### Pipeline Call from Route

```python
# In api/v1/routes/runs.py
from fastapi import BackgroundTasks, Depends
from sqlmodel import Session
from provenance.models.database import get_session
from provenance.core.pipeline import RunPipeline
from provenance.config import get_settings

@router.post("/runs", response_model=RunRead)
def create_run(
    run_in: RunCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    settings = Depends(get_settings),
):
    run = run_service.create(run_in, session)
    background_tasks.add_task(_run_pipeline, run.id, settings)
    return run

def _run_pipeline(run_id: int, settings):
    """Adapter from sync BackgroundTask to async pipeline."""
    import asyncio
    from provenance.models.database import engine
    with Session(engine) as session:
        pipeline = RunPipeline(settings=settings, session=session)
        asyncio.run(pipeline.execute(run_id))
```

Design note: FastAPI background tasks are synchronous functions. The adapter function `_run_pipeline` creates a new event loop and Session. This is safe because the background task runs in a thread pool, not the main thread. The Session created here is isolated from the request Session.

---

## 10. Low-Level Design: Divergence Engine

### `core/divergence.py`

The divergence engine reads from QueryProbe, LLMSignal, and DemandSignal and writes to DivergenceScore. All computation is read-time over raw data.

#### Formulae

**demand_llm_alignment_score** (0.0 to 1.0):

Let:
- `search_volume` = normalized demand score for the entity (0-100, rescaled to 0-1)
- `avg_rank` = mean recommendation_rank across all probes in the run for this entity (lower = better)
- `max_rank` = 5 (assumed max rank depth tracked; ranks above this treated as absent)
- `mention_rate` = (probes where mention_type != "absent") / total_probes

Then:
```
rank_score = 1.0 - min(avg_rank - 1, max_rank - 1) / (max_rank - 1)
             (if avg_rank is None/absent: rank_score = 0.0)

alignment_score = (search_volume_normalized * 0.4) + (rank_score * 0.4) + (mention_rate * 0.2)
```

Weights (0.4 / 0.4 / 0.2) are v1 defaults, configurable in a later version.

**divergence_direction** (categorical):

```
if alignment_score >= 0.7:
    direction = "aligned"
elif rank_score > search_volume_normalized + 0.2:
    direction = "llm_ahead"
else:
    direction = "demand_ahead"
```

"LLM ahead" = LLM recommends strongly but demand signal is weak.
"Demand ahead" = strong demand signal but LLM under-recommends.

**cross_query_stability** (0.0 to 1.0):

Let `ranks` = list of recommendation_rank values across all query variants for this entity (None = treated as max_rank + 1 = 6).

```
if len(ranks) <= 1:
    stability = 1.0
else:
    import statistics
    rank_range = max(ranks_filled) - min(ranks_filled)
    # rank_range of 0 = perfect stability, rank_range of 5 = max instability
    stability = 1.0 - (rank_range / 5.0)
    stability = max(0.0, min(1.0, stability))
```

---

```python
import json
import statistics
from typing import Optional
from sqlmodel import Session, select
from provenance.models.query_probe import QueryProbe
from provenance.models.llm_signal import LLMSignal
from provenance.models.demand_signal import DemandSignal
from provenance.models.divergence_score import DivergenceScore
from datetime import datetime

MAX_RANK = 5
ABSENT_RANK_PENALTY = MAX_RANK + 1  # 6 when absent


class DivergenceEngine:

    def __init__(self, session: Session):
        self.session = session

    def compute_and_store(self, run_id: int, entity_id: int) -> DivergenceScore:
        score = self._compute(run_id, entity_id)
        # Upsert: delete existing score for this run+entity, then insert
        existing = self.session.exec(
            select(DivergenceScore)
            .where(DivergenceScore.run_id == run_id)
            .where(DivergenceScore.entity_id == entity_id)
        ).first()
        if existing:
            self.session.delete(existing)
            self.session.commit()
        self.session.add(score)
        self.session.commit()
        self.session.refresh(score)
        return score

    def _compute(self, run_id: int, entity_id: int) -> DivergenceScore:
        # Fetch all probes for this run
        probes = self.session.exec(
            select(QueryProbe).where(QueryProbe.run_id == run_id)
        ).all()
        probe_ids = [p.id for p in probes]

        # Fetch LLM signals for this entity across all probes in run
        signals = self.session.exec(
            select(LLMSignal)
            .where(LLMSignal.entity_id == entity_id)
            .where(LLMSignal.probe_id.in_(probe_ids))
        ).all()

        # Fetch latest demand signal for this entity in this run
        demand = self.session.exec(
            select(DemandSignal)
            .where(DemandSignal.entity_id == entity_id)
            .where(DemandSignal.run_id == run_id)
            .order_by(DemandSignal.collected_at.desc())
        ).first()

        total_probes = len(probes)
        if total_probes == 0:
            return self._empty_score(run_id, entity_id)

        # --- rank_score ---
        ranks = []
        for sig in signals:
            if sig.recommendation_rank is not None:
                ranks.append(sig.recommendation_rank)
            else:
                ranks.append(ABSENT_RANK_PENALTY)

        avg_rank = statistics.mean(ranks) if ranks else ABSENT_RANK_PENALTY
        rank_score = 1.0 - min(avg_rank - 1, MAX_RANK - 1) / (MAX_RANK - 1)
        rank_score = max(0.0, min(1.0, rank_score))

        # --- mention_rate ---
        mentioned = sum(1 for s in signals if s.mention_type != "absent")
        mention_rate = mentioned / total_probes if total_probes > 0 else 0.0

        # --- demand normalized ---
        search_volume_normalized = 0.0
        if demand and demand.search_volume is not None:
            search_volume_normalized = demand.search_volume / 100.0

        # --- alignment score ---
        alignment_score = (
            search_volume_normalized * 0.4
            + rank_score * 0.4
            + mention_rate * 0.2
        )
        alignment_score = round(max(0.0, min(1.0, alignment_score)), 4)

        # --- divergence direction ---
        if alignment_score >= 0.7:
            direction = "aligned"
        elif rank_score > search_volume_normalized + 0.2:
            direction = "llm_ahead"
        else:
            direction = "demand_ahead"

        # --- cross-query stability ---
        ranks_filled = ranks  # already filled ABSENT_RANK_PENALTY above
        if len(ranks_filled) <= 1:
            stability = 1.0
        else:
            rank_range = max(ranks_filled) - min(ranks_filled)
            stability = 1.0 - (rank_range / float(MAX_RANK))
            stability = max(0.0, min(1.0, stability))
        stability = round(stability, 4)

        # --- mention type distribution ---
        mention_dist = {}
        for sig in signals:
            mt = sig.mention_type
            mention_dist[mt] = mention_dist.get(mt, 0) + 1

        return DivergenceScore(
            run_id=run_id,
            entity_id=entity_id,
            computed_at=datetime.utcnow(),
            demand_llm_alignment_score=alignment_score,
            divergence_direction=direction,
            cross_query_stability=stability,
            average_recommendation_rank=round(avg_rank, 2),
            mention_type_distribution_json=json.dumps(mention_dist),
            probes_included=total_probes,
        )

    def _empty_score(self, run_id: int, entity_id: int) -> DivergenceScore:
        return DivergenceScore(
            run_id=run_id,
            entity_id=entity_id,
            computed_at=datetime.utcnow(),
            demand_llm_alignment_score=0.0,
            divergence_direction="demand_ahead",
            cross_query_stability=0.0,
            probes_included=0,
        )
```

---

## 11. Low-Level Design: Competitor Delta and Gap Analysis

### `core/analysis.py`

#### Fingerprint

A Fingerprint is the assembled signal vector for one entity from one run. It is a Pydantic model (not a SQLModel table â€” it is a computed read-time object).

```python
from pydantic import BaseModel
from typing import Optional, List, Dict

class EntityFingerprint(BaseModel):
    entity_id: int
    entity_name: str
    run_id: int

    # Demand signals
    search_volume: Optional[float]
    trend_velocity: Optional[float]
    related_queries: List[str]
    geographic_distribution: Dict[str, float]

    # LLM signals (aggregated across probes for this run)
    average_recommendation_rank: Optional[float]  # lower = better
    mention_rate: float                            # 0-1
    primary_mention_rate: float                    # probes where mention_type == "primary" / total
    phrasing_sentiment_distribution: Dict[str, float]  # {"positive": 0.6, "neutral": 0.3, ...}
    top_co_mentioned: List[str]                    # top 5 co-mentioned entities by frequency
    cross_query_stability: float

    # Divergence
    alignment_score: float
    divergence_direction: str
```

#### FingerprintBuilder

```python
class FingerprintBuilder:

    def __init__(self, session: Session):
        self.session = session

    def build(self, entity_id: int, run_id: int) -> EntityFingerprint:
        entity = self.session.get(Entity, entity_id)
        demand = self.session.exec(
            select(DemandSignal)
            .where(DemandSignal.entity_id == entity_id)
            .where(DemandSignal.run_id == run_id)
        ).first()
        divergence = self.session.exec(
            select(DivergenceScore)
            .where(DivergenceScore.entity_id == entity_id)
            .where(DivergenceScore.run_id == run_id)
        ).first()
        probes = self.session.exec(
            select(QueryProbe).where(QueryProbe.run_id == run_id)
        ).all()
        probe_ids = [p.id for p in probes]
        signals = self.session.exec(
            select(LLMSignal)
            .where(LLMSignal.entity_id == entity_id)
            .where(LLMSignal.probe_id.in_(probe_ids))
        ).all()

        # Aggregate LLM signals
        ranks = [s.recommendation_rank for s in signals if s.recommendation_rank]
        avg_rank = sum(ranks) / len(ranks) if ranks else None
        mention_rate = sum(1 for s in signals if s.mention_type != "absent") / len(probes) if probes else 0.0
        primary_rate = sum(1 for s in signals if s.mention_type == "primary") / len(probes) if probes else 0.0

        sentiment_dist: Dict[str, int] = {}
        co_mention_counts: Dict[str, int] = {}
        for sig in signals:
            if sig.phrasing_sentiment:
                sentiment_dist[sig.phrasing_sentiment] = sentiment_dist.get(sig.phrasing_sentiment, 0) + 1
            for co in json.loads(sig.co_mentioned_entities_json or "[]"):
                co_mention_counts[co] = co_mention_counts.get(co, 0) + 1

        total_signals = len(signals) or 1
        sentiment_pct = {k: round(v / total_signals, 3) for k, v in sentiment_dist.items()}
        top_co = sorted(co_mention_counts, key=co_mention_counts.get, reverse=True)[:5]

        return EntityFingerprint(
            entity_id=entity_id,
            entity_name=entity.name,
            run_id=run_id,
            search_volume=demand.search_volume if demand else None,
            trend_velocity=demand.trend_velocity if demand else None,
            related_queries=json.loads(demand.related_queries_json) if demand else [],
            geographic_distribution=json.loads(demand.geographic_distribution_json) if demand else {},
            average_recommendation_rank=avg_rank,
            mention_rate=mention_rate,
            primary_mention_rate=primary_rate,
            phrasing_sentiment_distribution=sentiment_pct,
            top_co_mentioned=top_co,
            cross_query_stability=divergence.cross_query_stability if divergence else 0.0,
            alignment_score=divergence.demand_llm_alignment_score if divergence else 0.0,
            divergence_direction=divergence.divergence_direction if divergence else "demand_ahead",
        )
```

---

#### Competitor Delta

The delta is a field-by-field diff of two fingerprints. Each field gets a direction ("entity_leads", "competitor_leads", "parity") and a magnitude.

```python
from pydantic import BaseModel
from typing import Optional

class FieldDelta(BaseModel):
    field: str
    entity_value: Optional[float]
    competitor_value: Optional[float]
    delta: Optional[float]           # entity - competitor
    direction: str                   # "entity_leads" | "competitor_leads" | "parity"

class CompetitorDeltaResult(BaseModel):
    entity_id: int
    competitor_entity_id: int
    entity_run_id: int
    competitor_run_id: int
    deltas: list[FieldDelta]
    summary_advantage_fields: list[str]   # fields where entity_leads
    summary_gap_fields: list[str]         # fields where competitor_leads

class CompetitorDeltaService:

    def compute(
        self,
        entity_fp: EntityFingerprint,
        competitor_fp: EntityFingerprint,
    ) -> CompetitorDeltaResult:
        NUMERIC_FIELDS = [
            "search_volume",
            "trend_velocity",
            "average_recommendation_rank",
            "mention_rate",
            "primary_mention_rate",
            "cross_query_stability",
            "alignment_score",
        ]
        # Note: recommendation_rank is inverted â€” lower is better
        INVERTED_FIELDS = {"average_recommendation_rank"}

        deltas = []
        for field in NUMERIC_FIELDS:
            ev = getattr(entity_fp, field, None)
            cv = getattr(competitor_fp, field, None)
            if ev is None and cv is None:
                continue
            ev_f = float(ev) if ev is not None else 0.0
            cv_f = float(cv) if cv is not None else 0.0
            raw_delta = ev_f - cv_f
            if field in INVERTED_FIELDS:
                # Lower rank = better, so we invert the advantage interpretation
                if abs(raw_delta) < 0.1:
                    direction = "parity"
                elif raw_delta < 0:
                    direction = "entity_leads"
                else:
                    direction = "competitor_leads"
            else:
                if abs(raw_delta) < 0.05:
                    direction = "parity"
                elif raw_delta > 0:
                    direction = "entity_leads"
                else:
                    direction = "competitor_leads"

            deltas.append(FieldDelta(
                field=field,
                entity_value=ev_f,
                competitor_value=cv_f,
                delta=round(raw_delta, 4),
                direction=direction,
            ))

        advantages = [d.field for d in deltas if d.direction == "entity_leads"]
        gaps = [d.field for d in deltas if d.direction == "competitor_leads"]

        return CompetitorDeltaResult(
            entity_id=entity_fp.entity_id,
            competitor_entity_id=competitor_fp.entity_id,
            entity_run_id=entity_fp.run_id,
            competitor_run_id=competitor_fp.run_id,
            deltas=deltas,
            summary_advantage_fields=advantages,
            summary_gap_fields=gaps,
        )
```

---

#### Gap Analysis

Gap analysis prioritizes the competitor delta gaps by estimated impact on alignment_score. Fields are ranked by how much improvement is possible and how directly they connect to LLM recommendation behavior.

```python
FIELD_IMPACT_WEIGHTS = {
    # How much improving this field is estimated to affect LLM recommendation rank
    "average_recommendation_rank": 1.0,
    "mention_rate": 0.9,
    "primary_mention_rate": 0.85,
    "alignment_score": 0.8,
    "cross_query_stability": 0.6,
    "search_volume": 0.5,
    "trend_velocity": 0.3,
}

class GapItem(BaseModel):
    field: str
    entity_value: Optional[float]
    competitor_value: Optional[float]
    gap_magnitude: float        # abs(delta)
    impact_weight: float
    priority_score: float       # gap_magnitude * impact_weight
    action_hint: str            # human-readable guidance

ACTION_HINTS = {
    "average_recommendation_rank": "Improve LLM rank through authoritative content and citation signals",
    "mention_rate": "Increase entity visibility in LLM responses via broader content coverage",
    "primary_mention_rate": "Position entity as primary recommendation through use-case specificity",
    "alignment_score": "Align demand signals with LLM behavior through content and authority building",
    "cross_query_stability": "Improve consistency across query framings via clear entity positioning",
    "search_volume": "Increase search demand through SEO and brand awareness efforts",
    "trend_velocity": "Drive trend momentum through launches, publications, and community presence",
}

class GapAnalyzer:

    def analyze(self, delta_result: CompetitorDeltaResult) -> list[GapItem]:
        gaps = []
        for d in delta_result.deltas:
            if d.direction != "competitor_leads":
                continue
            magnitude = abs(d.delta) if d.delta is not None else 0.0
            weight = FIELD_IMPACT_WEIGHTS.get(d.field, 0.1)
            priority = round(magnitude * weight, 4)
            gaps.append(GapItem(
                field=d.field,
                entity_value=d.entity_value,
                competitor_value=d.competitor_value,
                gap_magnitude=round(magnitude, 4),
                impact_weight=weight,
                priority_score=priority,
                action_hint=ACTION_HINTS.get(d.field, "Investigate this signal gap"),
            ))

        # Sort by priority descending
        gaps.sort(key=lambda g: g.priority_score, reverse=True)
        return gaps
```

---

## 12. Low-Level Design: API Layer

All routes are in `api/v1/routes/`. Route handlers contain no logic â€” they call service functions only. All request/response types are Pydantic models.

### Route Summary

#### `api/v1/routes/entities.py`

| Method | Path | Request | Response | Description |
|--------|------|---------|----------|-------------|
| POST | `/v1/entities` | `EntityCreate` | `EntityRead` | Create entity |
| GET | `/v1/entities` | query: `skip`, `limit` | `List[EntityRead]` | List entities |
| GET | `/v1/entities/{entity_id}` | â€” | `EntityRead` | Get entity |
| PATCH | `/v1/entities/{entity_id}` | `EntityUpdate` | `EntityRead` | Update entity |
| DELETE | `/v1/entities/{entity_id}` | â€” | `{"deleted": true}` | Delete entity |

#### `api/v1/routes/runs.py`

| Method | Path | Request | Response | Description |
|--------|------|---------|----------|-------------|
| POST | `/v1/runs` | `RunCreate` | `RunRead` | Create + start run |
| GET | `/v1/runs/{run_id}` | â€” | `RunRead` | Get run status |
| GET | `/v1/entities/{entity_id}/runs` | query: `skip`, `limit` | `List[RunRead]` | List runs for entity |
| GET | `/v1/runs/{run_id}/probes` | â€” | `List[QueryProbeRead]` | Get all probes for run |
| GET | `/v1/runs/{run_id}/signals` | â€” | `List[LLMSignalRead]` | Get LLM signals for run |
| GET | `/v1/runs/{run_id}/demand` | â€” | `List[DemandSignalRead]` | Get demand signals for run |
| GET | `/v1/runs/{run_id}/citations` | â€” | `List[CitationRead]` | Get citations for run |
| GET | `/v1/runs/{run_id}/divergence` | â€” | `List[DivergenceScoreRead]` | Get divergence scores for run |

#### `api/v1/routes/analysis.py`

| Method | Path | Request | Response | Description |
|--------|------|---------|----------|-------------|
| GET | `/v1/entities/{entity_id}/fingerprint` | query: `run_id` (optional) | `EntityFingerprint` | Get fingerprint for entity |
| POST | `/v1/analysis/competitor-delta` | `CompetitorDeltaRequest` | `CompetitorDeltaResult` | Diff two entity fingerprints |
| POST | `/v1/analysis/gap` | `GapAnalysisRequest` | `List[GapItem]` | Prioritized gap list |

#### `CompetitorDeltaRequest` and `GapAnalysisRequest`

```python
class CompetitorDeltaRequest(BaseModel):
    entity_id: int
    competitor_entity_id: int
    entity_run_id: Optional[int] = None       # defaults to latest completed run
    competitor_run_id: Optional[int] = None   # defaults to latest completed run

class GapAnalysisRequest(BaseModel):
    entity_id: int
    competitor_entity_id: int
    entity_run_id: Optional[int] = None
    competitor_run_id: Optional[int] = None
```

#### Error Response Standard

All routes return structured errors:

```python
class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    code: str  # e.g. "ENTITY_NOT_FOUND", "RUN_NOT_COMPLETED"
```

HTTP exceptions raised in the service layer are caught by a FastAPI exception handler registered in `main.py`.

---

## 13. Alembic Migration Strategy

### Initialization

```bash
alembic init migrations
```

`alembic.ini` â€” set `sqlalchemy.url` to read from environment (not hardcoded):

```ini
# In env.py, override the URL from settings
from provenance.config import get_settings
config.set_main_option("sqlalchemy.url", get_settings().database_url)
```

`migrations/env.py` â€” import all SQLModel models to populate metadata:

```python
from provenance.models import entity, run, query_probe, llm_signal, demand_signal, citation, divergence_score
from sqlmodel import SQLModel
target_metadata = SQLModel.metadata
```

### Migration Sequence

| Migration | Name | Tables Created |
|-----------|------|----------------|
| 001 | `initial_schema` | entity, run, query_probe, llm_signal, demand_signal, citation, divergence_score |

All tables are created in a single initial migration. Subsequent migrations track any schema additions.

### Key Alembic Rules

1. Never use `SQLModel.metadata.create_all()` in production â€” that is only for dev/test.
2. Every PR that touches `models/` must include a corresponding Alembic migration.
3. Migration files are committed to the repository.
4. `alembic upgrade head` is the only way schema changes are applied.

---

## 14. Test Strategy

### Layer Strategy

| Layer | Test Type | Mock vs. Real |
|-------|-----------|---------------|
| Models | Unit | Real SQLite in-memory |
| Collectors | Unit | Mock pytrends (return fixture data) |
| Probes | Unit | Mock Anthropic client |
| Pipeline | Integration | Mock probe + collector; real SQLite in-memory |
| Divergence | Unit | Real SQLite in-memory with fixture data |
| Analysis | Unit | Fixture fingerprints |
| API routes | Integration | TestClient; mock pipeline trigger |

### Test File Structure

```
tests/
â”œâ”€â”€ conftest.py                    # Shared fixtures: in-memory engine, session, client
â”œâ”€â”€ test_models/
â”‚   â”œâ”€â”€ test_entity.py
â”‚   â””â”€â”€ test_run.py
â”œâ”€â”€ test_probes/
â”‚   â”œâ”€â”€ test_anthropic.py
â”‚   â”œâ”€â”€ test_openai_stub.py
â”‚   â””â”€â”€ test_gemini_stub.py
â”œâ”€â”€ test_collectors/
â”‚   â”œâ”€â”€ test_demand.py
â”‚   â””â”€â”€ test_citation.py
â”œâ”€â”€ test_core/
â”‚   â”œâ”€â”€ test_registry.py
â”‚   â”œâ”€â”€ test_pipeline.py
â”‚   â””â”€â”€ test_divergence.py
â”œâ”€â”€ test_analysis/
â”‚   â”œâ”€â”€ test_fingerprint.py
â”‚   â”œâ”€â”€ test_competitor_delta.py
â”‚   â””â”€â”€ test_gap_analysis.py
â””â”€â”€ test_api/
    â”œâ”€â”€ test_entities.py
    â”œâ”€â”€ test_runs.py
    â””â”€â”€ test_analysis.py
```

---

### `conftest.py` (critical shared fixtures)

```python
import pytest
from sqlmodel import SQLModel, create_engine, Session
from fastapi.testclient import TestClient
from provenance.main import app
from provenance.models.database import get_session

@pytest.fixture(name="engine")
def engine_fixture():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)

@pytest.fixture(name="session")
def session_fixture(engine):
    with Session(engine) as session:
        yield session

@pytest.fixture(name="client")
def client_fixture(session):
    def override_get_session():
        yield session
    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
```

---

### Critical Test Cases

#### Probes

1. `AnthropicProbe.probe()` â€” mock `anthropic.Anthropic.messages.create`, verify `ProbeResult` fields populated correctly
2. `AnthropicProbe._extract_entities()` â€” pass a canned response string, assert extracted entity has correct `mention_type` and `recommendation_rank`
3. `AnthropicProbe.probe()` with API error â€” assert `ProbeResult.error` is set, no exception raised
4. `OpenAIProbe.probe()` â€” assert returns stub `ProbeResult` with `error="stub"`

#### Collectors

5. `DemandCollector.collect()` â€” mock `TrendReq`, verify `DemandResult` fields from fixture DataFrame
6. `DemandCollector.collect()` on pytrends error â€” assert `DemandResult.error` set, no exception
7. `CitationExtractor.collect()` â€” pass response string with known URLs, assert correct domains and content_type inference
8. `CitationExtractor.collect()` with no URLs â€” assert returns empty list

#### Pipeline

9. Full pipeline with mocked probe and collector â€” assert Run transitions to `completed`, QueryProbe rows exist, LLMSignal rows exist, DemandSignal rows exist
10. Pipeline with probe error â€” assert Run transitions to `failed`, `error_message` populated
11. Pipeline isolation mode â€” assert only `anthropic` probe called
12. Pipeline aggregate mode â€” assert all registered probes called

#### Divergence

13. `DivergenceEngine.compute_and_store()` with perfect alignment â€” assert `direction="aligned"`, `alignment_score >= 0.7`
14. With entity absent from all probes â€” assert `direction="demand_ahead"`, `alignment_score` low, `cross_query_stability` low
15. With consistent rank 1 across all variants â€” assert `cross_query_stability == 1.0`
16. With rank oscillating 1 and 5 â€” assert `cross_query_stability == 0.2`

#### Analysis

17. `FingerprintBuilder.build()` â€” fixture run with known signals, assert all fingerprint fields computed correctly
18. `CompetitorDeltaService.compute()` â€” two fixture fingerprints where competitor leads on `mention_rate`, assert delta direction correct
19. `GapAnalyzer.analyze()` â€” fixture delta result, assert gaps sorted by priority_score descending
20. `GapAnalyzer.analyze()` with no gaps (entity leads on all fields) â€” assert returns empty list

#### API

21. `POST /v1/entities` â€” create entity, assert 201 and `EntityRead` response
22. `GET /v1/entities/{id}` â€” 404 for missing entity
23. `POST /v1/runs` â€” mock background task, assert 201 and `RunRead` with `status=pending`
24. `GET /v1/runs/{id}` â€” assert status field reflects db state
25. `GET /v1/runs/{id}/divergence` â€” with completed run fixture, returns `DivergenceScoreRead`
26. `POST /v1/analysis/competitor-delta` â€” fixture entities with runs, returns delta
27. `POST /v1/analysis/gap` â€” fixture entities with runs, returns prioritized gaps

---

## 15. Risk Areas

### Risk 1: pytrends Rate Limiting and Fragility

pytrends hits an unofficial Google API. It has no SLA, changes without notice, and rate-limits aggressively.

Mitigations:
- Always sleep between pytrends calls (`pytrends_request_delay_seconds`, default 1.0)
- Wrap every `pytrends` call in `try/except` and return `DemandResult` with `error` field set â€” never let a demand collection failure crash a run
- Mock pytrends in all tests â€” never hit the real API in CI
- Design `DemandSignal` so all fields are `Optional` â€” a run with no demand data is valid and can still produce partial divergence scores

---

### Risk 2: Anthropic Extraction Pass Cost and Latency

Every probe generates a second Anthropic call for structured extraction. With 4 query variants per run, that is 8 total Anthropic API calls per run (isolation mode). In aggregate mode (3 providers): 4 probe calls + 4 extraction calls = 8, but only the Anthropic ones do real extraction â€” stubs return empty lists.

Mitigations:
- Set `temperature=0.0` on extraction to reduce token variance
- Cap `max_tokens=1000` on extraction calls
- If extraction call fails, log it and return empty entity list (do not fail the probe row)
- In v2, replace with Anthropic tool use / structured JSON output to merge probe + extraction into one call

---

### Risk 3: Background Task Session Lifetime

FastAPI background tasks run after the HTTP response is sent. The `Session` from the request context is closed by then. A new `Session` must be created explicitly in the background task adapter.

The pattern in this plan (create a new `Session` inside `_run_pipeline` using `engine` directly) is correct and must not be changed to reuse the request session. This is a common source of subtle `DetachedInstanceError` bugs in SQLModel/SQLAlchemy.

Mitigation: The `_run_pipeline` adapter function always creates its own `Session`. No model instances from the request scope are passed into the background task.

---

### Risk 4: Divergence Score Is a Cached Derived Table

`DivergenceScore` can be stale if re-run logic is added in v2. The upsert pattern (delete existing, insert new) in `DivergenceEngine.compute_and_store()` handles recomputation cleanly.

Do not add triggers or computed columns to this table. All computation must remain in Python, not SQL. This preserves the ability to swap databases.

---

### Risk 5: Competitor Entity Resolution in LLMSignal

When the probe extracts signal for a competitor entity (e.g. "Neo4j"), that competitor may not have an `Entity` row in the database. In v1, `_resolve_entity_id()` returns `None` for unknown competitors, and no `LLMSignal` row is written for them. Co-mention data is still captured in `co_mentioned_entities_json` on the primary entity's signal.

This is a deliberate scope constraint. It means competitor analysis requires the competitor to be registered as an `Entity` and have its own run. This is by design â€” the value of Provenance is in running the full pipeline for each entity, not in inferring competitor signals from a single probe.

---

### Risk 6: SQLite Concurrency in Background Tasks

SQLite with `check_same_thread=False` allows multiple threads to access the same database, but SQLite's write lock is serialized. If two runs execute simultaneously, one will wait on the other's write lock.

This is acceptable in v1 (single-user tool). When moving to Postgres in v2, this resolves automatically. Do not add concurrency workarounds in v1 â€” they are not needed and would complicate the Postgres migration.

---

### Risk 7: Alembic Autogenerate and JSON Columns

SQLModel columns using `sa_column_kwargs` (like `competitors_json`) may not be picked up correctly by `alembic revision --autogenerate`. Always review autogenerated migrations before committing. Column names must match between the Python model and the migration.

Mitigation: After generating a migration with `--autogenerate`, review the `upgrade()` function manually and verify it matches the intended schema. Add the review step to the PR checklist.

---

### Critical Files for Implementation

- `C:\Users\mehul\Documents\Projects - GIT\Prevenance\CLAUDE.md` - Architecture constraints and coding conventions that all implementation must follow; any implementation decision must be cross-checked here
- `C:\Users\mehul\Documents\Projects - GIT\Prevenance\thesis\thesis_20260315.md` - Product source of truth; divergence model, signal families, and data philosophy are defined here and must drive every schema and algorithm decision
- `C:\Users\mehul\Documents\Projects - GIT\Prevenance\TASK.md` - Task log that must be updated at the start of every implementation session before any code is written

The three files above are the only files that currently exist. The following paths are the highest-leverage files to implement first, based on the dependency order in this plan:

- `provenance/config.py` - All settings; nothing else can be instantiated without it, and hardcoding any value is a constraint violation
- `provenance/models/query_probe.py` - Widest and most architecturally significant table; getting the flat-column ProbeContext schema right before any probe code is written prevents a painful migration
- `provenance/core/pipeline.py` - Central orchestrator; its interface and session-lifecycle decisions constrain how probes, collectors, routes, and background tasks are written