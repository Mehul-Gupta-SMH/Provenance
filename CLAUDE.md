# Provenance — Claude Code Instructions

## What This Project Is

**Provenance** is a signal intelligence tool that makes LLM recommendation behavior observable, measurable, and actionable. It answers: *why does an LLM recommend X over Y, and what would it take to change that?*

The source of truth for product decisions is `thesis/thesis_20260315.md`. All implementation decisions must be traceable back to it.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| API | FastAPI, versioned under `/v1/` |
| ORM | SQLModel (SQLAlchemy + Pydantic unified) |
| DB | SQLite (dev/v1), designed to swap to Postgres with zero schema change |
| Migrations | Alembic — every schema change tracked, no manual ALTER TABLE |
| LLM (primary) | Anthropic / Claude SDK |
| LLM (stubbed) | OpenAI, Gemini — registry drop-ins for v2 |
| Demand signals | pytrends (Google Trends) |
| Task queue | FastAPI background tasks (v1), Celery/Redis in v2 |

---

## Architecture Constraints

These are non-negotiable. Do not violate them.

1. **API-first.** All business logic lives in the FastAPI service. No logic outside the API layer.
2. **Registry pattern.** LLM probes and signal collectors are registered implementations of abstract base classes. Adding a provider = drop-in, not a refactor.
3. **Flat schema, late derivation.** Raw probe data is never aggregated at write time. All segmentation, persona-based analysis, and cross-dimensional queries are read-time operations over flat tables.
4. **No premature aggregation.** Do not bucket or fold variables at write time. The schema must support any future aggregation without a migration.
5. **Versioned API.** All routes under `/v1/`. Breaking changes get a new version prefix.
6. **Migrations from day one.** Every schema change via Alembic. Never hand-edit the DB.

---

## Project Structure

```
provenance/
├── api/
│   └── v1/
│       └── routes/         # One file per resource (entities, runs, signals, etc.)
├── core/
│   ├── registry.py         # LLM probe + signal collector registry
│   ├── pipeline.py         # Run orchestration
│   └── divergence.py       # Divergence score computation (read-time)
├── models/
│   └── *.py                # SQLModel table definitions (flat, raw)
├── collectors/
│   ├── base.py             # Abstract base for signal collectors
│   ├── demand.py           # pytrends collector
│   └── citation.py         # Citation extractor
├── probes/
│   ├── base.py             # Abstract base for LLM probes
│   ├── anthropic.py        # Claude probe (functional in v1)
│   ├── openai.py           # Stubbed
│   └── gemini.py           # Stubbed
├── migrations/             # Alembic migration scripts
├── tests/
├── main.py                 # FastAPI app entry point
└── config.py               # Settings (env-based)
```

---

## Key Domain Concepts

| Term | Definition |
|------|------------|
| Entity | The brand, product, tool, or concept being tracked |
| Run | A full pipeline execution for an entity |
| QueryProbe | A single LLM call: one query variant × one model |
| ProbeContext | Full context of a QueryProbe (temporal, geo, persona, LLM params) |
| Fingerprint | Assembled feature vector for an entity from a run |
| Divergence | Gap between demand baseline and LLM recommendation |

---

## V1 Scope Boundaries

**In scope:** Entity CRUD, run execution (background tasks), Claude probe (functional), OpenAI/Gemini (stubbed), demand signals (pytrends), citation extraction, divergence score, competitor delta, gap analysis, full `/v1/` API surface, SQLite, Alembic.

**Out of scope:** Dashboard/frontend, auth/multi-tenancy, backlink signals, temporal drift viz, Celery/Redis, Postgres, deployment/containerization.

---

## Coding Conventions

- Python 3.11+
- Type hints everywhere
- Pydantic models for all API request/response shapes (SQLModel for DB models)
- No logic in route handlers — routes call service functions only
- Tests live in `tests/` mirroring the source structure
- Environment variables via `config.py` using `pydantic-settings`
- Never hardcode API keys or model names in source — always via config

---

## Git Workflow

- Never push directly to `main`
- Use feature branches (`feat/`, `fix/`, `chore/` prefixes)
- **All commits and PRs are handled via `codex` CLI** — do not use raw git commit / gh pr create
