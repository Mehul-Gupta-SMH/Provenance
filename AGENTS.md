# Provenance — Agent Guidelines

Instructions for AI agents (Claude Code and future agentic consumers) working on this codebase.

---

## Codebase Orientation

Before writing any code, read:
1. `thesis/thesis_20260315.md` — product thesis and source of truth
2. `CLAUDE.md` — tech stack, architecture constraints, project structure
3. `TASK.md` — current task state and in-progress work

---

## When Adding a New LLM Provider

1. Create `probes/<provider>.py` implementing the abstract base in `probes/base.py`
2. Register it in `core/registry.py` — do not modify the pipeline
3. Add provider config to `config.py`
4. Stub test in `tests/probes/test_<provider>.py`

Never hardwire a provider name anywhere outside the registry.

---

## When Adding a New Signal Collector

Same pattern as LLM providers:
1. Implement `collectors/base.py` abstract base
2. Register in `core/registry.py`
3. Add flat columns to the relevant SQLModel table
4. Write Alembic migration — never alter the DB manually

---

## Schema Changes

- All schema changes require an Alembic migration
- Columns must be additive where possible — do not rename or drop in v1
- Derived/computed signals (e.g., divergence) are never stored as raw columns — they are computed at read time from flat probe data

---

## API Changes

- All routes must live under `/v1/`
- Request and response shapes must be Pydantic models
- No business logic in route handlers — delegate to service layer
- New endpoints must not break the existing API surface

---

## Testing Guidelines

- Unit tests for all service layer functions
- Integration tests for pipeline runs should use a real SQLite DB (in-memory or temp file), not mocks
- LLM probe tests may mock the LLM API call itself, but must exercise the full extraction logic

---

## Divergence Computation

Divergence scores (`demand_llm_alignment_score`, `divergence_direction`, `cross_query_stability`) are **always computed at read time** from flat QueryProbe and DemandSignal data. They are never stored as a primary source. Writing a divergence score to the DB is a cache, not a source of truth.

---

## What Not To Do

- Do not aggregate or bucket data at write time
- Do not add business logic outside the FastAPI service layer
- Do not hardcode model names, API keys, or provider identifiers in source
- Do not create a dashboard, auth layer, or multi-tenancy features in v1
- Do not introduce Celery, Redis, or Postgres in v1 — the architecture must support them later without requiring it now
