# Provenance

> *Trace why LLMs recommend what they do.*

---

## What Is This?

Search engine optimization was built on a simple premise: understand how Google ranks pages, then engineer content to rank higher. That premise is breaking.

LLMs are increasingly the first point of recommendation for tools, products, services, and concepts — especially in technical and B2B contexts. A developer asking Claude which graph database to use, an analyst asking GPT-4 which BI tool to evaluate. These are purchase-influencing moments. And unlike Google, the ranking function is opaque.

**Provenance** answers: *why does an LLM recommend X over Y — and what would it take to change that?*

This is not a prompt engineering problem. It is a signal intelligence problem.

---

## How It Works

LLM recommendations are a function of measurable signals:

```
f(entity_signals, query_context, probe_context, temporal_context, demand_context)
```

Provenance probes LLMs across query variants, extracts structured fingerprints from responses, and compares them against search demand baselines (Google Trends). The gap between the two is the **divergence signal**.

| Divergence State | Meaning | Value |
|-----------------|---------|-------|
| LLM ahead of demand | Model recommends before search volume catches up | Early signal |
| Demand ahead of LLM | High search volume, LLM under-recommends | Highest opportunity |
| Aligned | LLM echoes established consensus | Calibration anchor |

---

## Three Use Modes

- **Self-tracking** — Am I being recommended? At what rank? In what context? How is that drifting over time?
- **Competitor benchmarking** — Why does the LLM prefer Competitor A? What signals do they have that I don't?
- **Gap analysis** — A direct, prioritized content brief grounded in what the LLM actually cites.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| API | FastAPI (`/v1/`) |
| ORM + Schema | SQLModel |
| Database | SQLite (v1), Postgres-ready |
| Migrations | Alembic |
| LLM Probing | Anthropic Claude (v1), OpenAI + Gemini (stubbed) |
| Demand Signals | pytrends (Google Trends) |

---

## Architecture

Provenance is API-first: all business logic lives in the FastAPI service under `/v1/`, and route handlers contain no logic — they delegate to `services/` and `core/`. LLM probes (`probes/`) and signal collectors (`collectors/`) are registered implementations of abstract base classes (`core/registry.py`), so adding a provider is a drop-in, not a refactor. The schema is flat with late derivation: raw probe data (`QueryProbe`, `LLMSignal`, `DemandSignal`, `Citation`) is never aggregated at write time — segmentation, persona-based analysis, and cross-dimensional queries are all read-time operations, computed by `core/divergence.py` and `core/analysis.py` and cached only where explicitly noted (`DivergenceScore`). Every data point anchors to one of three join keys in a strict hierarchy: `Experiment` (cross-run grouping) → `Run` (one pipeline execution for one entity) → `QueryProbe` (one atomic LLM call, identified by `entry_id`). Per-probe signal tables reference `entry_id`, per-run tables reference `run_id`, and per-entity tables (future) reference `entity_id`. All schema changes go through Alembic — no hand-edited tables — and the SQLite-backed v1 schema is designed to swap to Postgres with zero migration changes.

---

## Project Structure

```
provenance/
├── api/v1/routes/      # One file per resource
├── core/               # Registry, pipeline orchestration, divergence engine
├── models/             # SQLModel table definitions (flat, raw)
├── collectors/         # Signal collectors (demand, citation)
├── probes/             # LLM probe implementations
├── migrations/         # Alembic migration scripts
├── tests/
├── main.py
└── config.py
```

---

## Key Documents

| File | Purpose |
|------|---------|
| [`thesis/thesis_20260315.md`](thesis/thesis_20260315.md) | Product thesis — source of truth for all decisions |
| [`PLAN.md`](PLAN.md) | Full LLD, phase plan, and test strategy |
| [`CLAUDE.md`](CLAUDE.md) | Architecture constraints and coding conventions |
| [`AGENTS.md`](AGENTS.md) | Guidelines for AI agents working on this codebase |

---

## Getting Started

```bash
# 1. Clone and install dependencies
git clone https://github.com/Mehul-Gupta-SMH/Provenance.git
cd Provenance
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Fill in ANTHROPIC_API_KEY and other values (see .env.example for the full list:
# ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, DATABASE_URL, APP_ENV, LOG_LEVEL)

# 3. Run migrations
alembic upgrade head

# 4. Start the API
uvicorn main:app --reload
```

API available at `http://localhost:8000/v1/`. Interactive docs (Swagger UI) at `http://localhost:8000/docs`.

### Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -q
```

The test suite runs entirely offline against an in-memory SQLite database — no API keys or network access required.

---

## API Reference

All routes are versioned under `/v1/`. Error responses use a structured body: `{"detail": {"error": "<CODE>", "detail": "<message>"}}`, with a matching HTTP status (404 for not-found, 422 for validation errors).

### Meta

| Method | Path | Description |
|--------|------|--------------|
| `GET` | `/health` | Liveness check. Returns `{"status": "ok", "version": "1.0.0"}`. |

### Entities (`/v1/entities`)

| Method | Path | Request | Response |
|--------|------|---------|----------|
| `POST` | `/v1/entities` | `EntityCreate`: `name`, `category`, `url?`, `competitors[]`, `query_seeds[]` | `201` `EntityRead` |
| `GET` | `/v1/entities` | Query: `skip` (≥0, default 0), `limit` (1-1000, default 100) | `200` `List[EntityRead]` |
| `GET` | `/v1/entities/{entity_id}` | — | `200` `EntityRead`, or `404 ENTITY_NOT_FOUND` |
| `PATCH` | `/v1/entities/{entity_id}` | `EntityUpdate`: any subset of `name`, `category`, `url`, `competitors`, `query_seeds` | `200` `EntityRead`, or `404 ENTITY_NOT_FOUND` |
| `GET` | `/v1/entities/{entity_id}/fingerprint` | Query: `run_id?` (defaults to latest completed run) | `200` `EntityFingerprint`, or `404 ENTITY_NOT_FOUND` / `404 RUN_NOT_COMPLETED` |
| `DELETE` | `/v1/entities/{entity_id}` | — | `200` `{"deleted": true}`, or `404 ENTITY_NOT_FOUND` |

### Experiments (`/v1/experiments`)

| Method | Path | Request | Response |
|--------|------|---------|----------|
| `POST` | `/v1/experiments` | `ExperimentCreate`: `name`, `description?`, `config_json?` | `201` `ExperimentRead` |
| `GET` | `/v1/experiments` | Query: `skip`, `limit` | `200` `List[ExperimentRead]` |
| `GET` | `/v1/experiments/{experiment_id}` | — | `200` `ExperimentRead`, or `404 EXPERIMENT_NOT_FOUND` |
| `GET` | `/v1/experiments/{experiment_id}/runs` | — | `200` `List[RunRead]`, or `404 EXPERIMENT_NOT_FOUND` |
| `GET` | `/v1/experiments/{experiment_id}/comparison` | — | `200` `ExperimentComparison` (per-run divergence snapshots + first→last metric deltas), or `404 EXPERIMENT_NOT_FOUND` |
| `GET` | `/v1/experiments/{experiment_id}/drift` | — | `200` `ExperimentDrift` (per-entity time series of alignment/rank/stability), or `404 EXPERIMENT_NOT_FOUND` |

### Runs (`/v1/runs`)

| Method | Path | Request | Response |
|--------|------|---------|----------|
| `POST` | `/v1/runs` | `RunCreate`: `entity_id`, `mode?` (`isolation` \| `aggregate`), `experiment_id?`, `probe_contexts?` (up to 10 `ProbeContextSpec` entries — persona/expertise/locale/temperature overrides; the pipeline fans out contexts × query variants) | `201` `RunRead` (`status=pending`); schedules pipeline execution as a background task. `404 ENTITY_NOT_FOUND` / `404 EXPERIMENT_NOT_FOUND` |
| `GET` | `/v1/runs/{run_id}` | — | `200` `RunRead`, or `404 RUN_NOT_FOUND` |
| `GET` | `/v1/runs` | Query: `entity_id?`, `skip`, `limit` | `200` `List[RunRead]` |
| `POST` | `/v1/runs/{run_id}/divergence` | — | `200` `DivergenceScore` (recomputes and upserts), or `404 RUN_NOT_FOUND` |
| `GET` | `/v1/runs/{run_id}/divergence` | — | `200` `DivergenceScore`, or `404 DIVERGENCE_NOT_FOUND` |
| `GET` | `/v1/runs/{run_id}/probes` | — | `200` `List[QueryProbeRead]` (raw per-probe observations), or `404 RUN_NOT_FOUND` |
| `GET` | `/v1/runs/{run_id}/signals` | — | `200` `List[LLMSignalRead]` (extracted recommendation signals; `co_mentioned_entities` deserialized), or `404 RUN_NOT_FOUND` |
| `GET` | `/v1/runs/{run_id}/citations` | — | `200` `List[CitationRead]`, or `404 RUN_NOT_FOUND` |
| `GET` | `/v1/runs/{run_id}/demand` | — | `200` `List[DemandSignalRead]` (`related_queries` / `geographic_distribution` deserialized), or `404 RUN_NOT_FOUND` |
| `GET` | `/v1/runs/{run_id}/datapoints` | Query: `signal_family?` | `200` `List[DataPointRead]` (EAV signal rows, e.g. `signal_family=social` HN mentions/points), or `404 RUN_NOT_FOUND` |

### Analysis (`/v1/analysis`)

| Method | Path | Request | Response |
|--------|------|---------|----------|
| `POST` | `/v1/analysis/competitor-delta` | `entity_id`, `competitor_entity_id`, `entity_run_id?`, `competitor_run_id?` | `200` `CompetitorDeltaResult` (per-field deltas + advantage/gap summaries), or `404 ENTITY_NOT_FOUND` / `404 RUN_NOT_COMPLETED` |
| `POST` | `/v1/analysis/gap` | Same request shape as competitor-delta | `200` `List[GapItem]`, sorted by `priority_score` descending, or same `404`s |

---

## V1 Scope

In scope: Entity CRUD · Run execution · Claude probing · Demand signals · Citation extraction · Divergence scoring · Competitor delta · Gap analysis · Full `/v1/` API

Out of scope: Frontend · Auth · Celery/Redis · Postgres · Deployment

---

## Contributing

- Never push directly to `main` — use feature branches and PRs
- All commits and PRs via `codex` CLI
- Read `CLAUDE.md` before writing any code
