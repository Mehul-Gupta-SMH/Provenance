# Provenance — Task Log

## Tasks

| Date | Status | Task | Files / Notes |
|------|--------|------|---------------|
| 2026-03-20 | [x] | Read and understand project thesis | `thesis/thesis_20260315.md` |
| 2026-03-20 | [x] | Create project scaffolding artifacts | `TASK.md`, `CLAUDE.md`, `AGENTS.md` |
| 2026-03-20 | [x] | Generate implementation plan (LLD + phases) | `PLAN.md` |
| 2026-03-20 | [x] | Update README | `README.md` |
| 2026-03-22 | [x] | Phase 0 — Foundation | `provenance/config.py`, `main.py`, `provenance/models/`, `provenance/probes/base.py`, `provenance/collectors/base.py`, `provenance/core/registry.py`, `alembic.ini`, `migrations/`, `pyproject.toml`, `requirements.txt`, `.gitignore` |
| 2026-03-22 | [x] | Extensible signal architecture | `provenance/models/experiment.py`, `provenance/models/data_point.py`, `Run.experiment_id`, `entry_id` join key convention, `CLAUDE.md` extensibility docs |
| 2026-07-16 | [x] | v1 planning reconciliation — PLAN.md v1.1 | Status section, plan-vs-code deltas (`entry_id`, dropped `entity_id` FKs, Experiment/DataPoint LLD), updated pipeline/divergence/analysis samples, fixed file encoding |
| 2026-07-16 | [x] | Phase 1+2 — Entity/Experiment CRUD + Run lifecycle | `provenance/api/v1/routes/{entities,experiments,runs}.py`, `provenance/services/` |
| 2026-07-16 | [x] | Phase 3 — Anthropic probe (two-pass, retry, soft-failure) | `provenance/probes/anthropic.py` |
| 2026-07-16 | [x] | Phase 4 — Demand + citation collectors | `provenance/collectors/{demand,citation}.py` |
| 2026-07-16 | [x] | Phase 5 — Pipeline orchestration + background task | `provenance/core/pipeline.py`, runs route hook |
| 2026-07-16 | [x] | Phase 6+7 — Divergence engine + analysis layer | `provenance/core/{divergence,analysis}.py`, `provenance/api/v1/routes/analysis.py`, fingerprint/divergence endpoints |
| 2026-07-16 | [x] | Phase 8 — Tests (78), lint clean, README API reference | `tests/` (18 files), `README.md` |
| 2026-07-18 | [x] | Raw signal-inspection endpoints (PLAN §12) | `provenance/services/signal_service.py`, `*Read` schemas on `query_probe`/`llm_signal`/`citation`/`demand_signal`, `GET /v1/runs/{id}/{probes,signals,citations,demand}` |
| 2026-07-18 | [x] | Probe context sweep (contexts × variants) | `ProbeContextSpec` + `Run.probe_contexts_json`, migration `d80a8f4d890f`, pipeline fan-out |
| 2026-07-18 | [x] | Experiment analytics layer | `provenance/core/experiment_analysis.py`, `GET /v1/experiments/{id}/{runs,comparison,drift}` |
| 2026-07-18 | [x] | Social collector → DataPoint EAV (first drop-in signal family, no migration) | `provenance/collectors/social.py`, `DataPointRead`, `GET /v1/runs/{id}/datapoints` |
| 2026-07-18 | [x] | Action report — actionability layer | `provenance/core/action_report.py`, `GET /v1/runs/{id}/report` |
| 2026-07-18 | [x] | Live run+test (real uvicorn/HTTP), docs refresh | 121 tests green; `README.md`, `.env.example`, `TASK.md` updated; PR #7 |