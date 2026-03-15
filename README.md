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
# Fill in ANTHROPIC_API_KEY and other values

# 3. Run migrations
alembic upgrade head

# 4. Start the API
uvicorn main:app --reload
```

API available at `http://localhost:8000/v1/`

---

## V1 Scope

In scope: Entity CRUD · Run execution · Claude probing · Demand signals · Citation extraction · Divergence scoring · Competitor delta · Gap analysis · Full `/v1/` API

Out of scope: Frontend · Auth · Celery/Redis · Postgres · Deployment

---

## Contributing

- Never push directly to `main` — use feature branches and PRs
- All commits and PRs via `codex` CLI
- Read `CLAUDE.md` before writing any code
