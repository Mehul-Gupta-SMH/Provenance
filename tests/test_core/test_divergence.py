"""Tests for provenance/core/divergence.py (PLAN.md section 14, Divergence 13-16).

QueryProbe/LLMSignal/DemandSignal rows are constructed directly against the
in-memory session; expected DivergenceScore values are computed by hand from
the formula in core/divergence.py.
"""
from __future__ import annotations

from sqlmodel import select

from provenance.core.divergence import DivergenceEngine
from provenance.models.demand_signal import DemandSignal
from provenance.models.divergence_score import DivergenceScore
from provenance.models.llm_signal import LLMSignal
from provenance.models.query_probe import QueryProbe
from provenance.models.run import Run, RunStatus

_VARIANTS = ("direct", "comparative", "expert", "contrarian")


def _make_run_with_probes(session, entity_id, probe_specs, demand=None):
    """probe_specs: list of (rank_or_none, mention_type, raw_response_override)."""
    run = Run(entity_id=entity_id, status=RunStatus.completed)
    session.add(run)
    session.commit()
    session.refresh(run)

    for i, (rank, mention_type, raw_override) in enumerate(probe_specs):
        variant = _VARIANTS[i % len(_VARIANTS)]
        qp = QueryProbe(
            run_id=run.id,
            query_variant=variant,
            query_text=f"q-{variant}",
            raw_response=raw_override if raw_override is not None else "ok",
        )
        session.add(qp)
        session.flush()  # populate qp.id
        session.add(LLMSignal(entry_id=qp.id, recommendation_rank=rank, mention_type=mention_type))
    session.commit()

    if demand is not None:
        session.add(DemandSignal(run_id=run.id, search_volume=demand))
        session.commit()

    return run


def test_divergence_perfect_alignment(session, make_entity):
    entity = make_entity()
    run = _make_run_with_probes(session, entity.id, [(1, "primary", None)] * 4, demand=100.0)

    score = DivergenceEngine(session).compute_for_run(run.id)

    assert score.divergence_direction == "aligned"
    assert score.demand_llm_alignment_score >= 0.7
    assert score.demand_llm_alignment_score == 1.0
    assert score.cross_query_stability == 1.0
    assert score.probes_included == 4


def test_divergence_entity_absent_from_all_probes(session, make_entity):
    entity = make_entity()
    run = _make_run_with_probes(session, entity.id, [(None, "absent", None)] * 4, demand=None)

    score = DivergenceEngine(session).compute_for_run(run.id)

    assert score.divergence_direction == "demand_ahead"
    assert score.demand_llm_alignment_score == 0.0
    # All four probes carry the same (penalized) absent rank, so cross-query
    # stability reflects consistency of that absence rather than oscillation —
    # this is the actual formula's behavior, distinct from the oscillation
    # case below which is where "low stability" is exercised.
    assert score.cross_query_stability == 1.0


def test_divergence_rank_consistent_at_one_is_fully_stable(session, make_entity):
    entity = make_entity()
    run = _make_run_with_probes(session, entity.id, [(1, "primary", None)] * 4, demand=50.0)

    score = DivergenceEngine(session).compute_for_run(run.id)

    assert score.cross_query_stability == 1.0


def test_divergence_rank_oscillating_one_and_five(session, make_entity):
    entity = make_entity()
    specs = [
        (1, "primary", None),
        (5, "alternative", None),
        (1, "primary", None),
        (5, "alternative", None),
    ]
    run = _make_run_with_probes(session, entity.id, specs, demand=50.0)

    score = DivergenceEngine(session).compute_for_run(run.id)

    assert score.cross_query_stability == 0.2


def test_divergence_zero_probes_returns_empty_score(session, make_entity):
    entity = make_entity()
    run = Run(entity_id=entity.id, status=RunStatus.completed)
    session.add(run)
    session.commit()
    session.refresh(run)

    score = DivergenceEngine(session).compute_for_run(run.id)

    assert score.probes_included == 0
    assert score.demand_llm_alignment_score == 0.0
    assert score.divergence_direction == "demand_ahead"
    assert score.cross_query_stability == 0.0


def test_divergence_all_error_probes_excluded(session, make_entity):
    entity = make_entity()
    run = _make_run_with_probes(
        session, entity.id, [(1, "primary", "[PROBE ERROR] boom")] * 4, demand=50.0
    )

    score = DivergenceEngine(session).compute_for_run(run.id)

    assert score.probes_included == 0
    assert score.divergence_direction == "demand_ahead"


def test_divergence_recompute_upserts_no_duplicate_rows(session, make_entity):
    entity = make_entity()
    run = _make_run_with_probes(session, entity.id, [(1, "primary", None)] * 4, demand=50.0)

    DivergenceEngine(session).compute_for_run(run.id)
    DivergenceEngine(session).compute_for_run(run.id)

    rows = session.exec(select(DivergenceScore).where(DivergenceScore.run_id == run.id)).all()
    assert len(rows) == 1
