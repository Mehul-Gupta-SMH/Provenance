"""
DivergenceEngine — read-time computation of DivergenceScore (PLAN.md section 10).

The cached DivergenceScore row is never a source of truth: compute_for_run always
re-derives from QueryProbe/LLMSignal/DemandSignal and upserts (delete-then-insert).
Per PLAN.md v1.1 delta #2, LLMSignal carries no entity_id — every signal for a run's
probes describes that run's own entity by construction, so signals are fetched via
`entry_id.in_(...)` with no entity filter, and DemandSignal is filtered by run_id only.

Probes whose raw_response starts with "[PROBE ERROR]" (pipeline.py's soft-failure
marker — see core/pipeline.py) carry no real signal and are excluded from every
count and average below, including probes_included.
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime
from typing import List

from sqlmodel import Session, select

from provenance.models.demand_signal import DemandSignal
from provenance.models.divergence_score import DivergenceScore
from provenance.models.llm_signal import LLMSignal
from provenance.models.query_probe import QueryProbe
from provenance.models.run import Run

MAX_RANK = 5
ABSENT_RANK_PENALTY = MAX_RANK + 1  # 6 — treated as "worse than the max tracked rank"
_PROBE_ERROR_PREFIX = "[PROBE ERROR]"


class RunNotFoundError(Exception):
    """Raised when compute_for_run is called with a run_id that does not exist."""


class DivergenceEngine:
    """Computes and upserts the single DivergenceScore row for a run."""

    def __init__(self, session: Session):
        self.session = session

    def compute_for_run(self, run_id: int) -> DivergenceScore:
        run = self.session.get(Run, run_id)
        if run is None:
            raise RunNotFoundError(f"Run {run_id} not found")

        score = self._compute(run_id, run.entity_id)

        existing = self.session.exec(
            select(DivergenceScore)
            .where(DivergenceScore.run_id == run_id)
            .where(DivergenceScore.entity_id == run.entity_id)
        ).first()
        if existing:
            self.session.delete(existing)
            self.session.commit()

        self.session.add(score)
        self.session.commit()
        self.session.refresh(score)
        return score

    def _compute(self, run_id: int, entity_id: int) -> DivergenceScore:
        probes = self.session.exec(select(QueryProbe).where(QueryProbe.run_id == run_id)).all()
        # Soft-failed probes carry no real signal — excluded everywhere, including
        # probes_included (pipeline.py marks them via the raw_response prefix).
        probes = [p for p in probes if not p.raw_response.startswith(_PROBE_ERROR_PREFIX)]
        total_probes = len(probes)
        if total_probes == 0:
            return self._empty_score(run_id, entity_id)

        entry_ids = [p.id for p in probes]
        signals = self.session.exec(
            select(LLMSignal).where(LLMSignal.entry_id.in_(entry_ids))
        ).all()

        demand = self.session.exec(
            select(DemandSignal)
            .where(DemandSignal.run_id == run_id)
            .order_by(DemandSignal.collected_at.desc())
        ).first()

        # --- rank_score ---
        ranks: List[int] = [
            s.recommendation_rank if s.recommendation_rank is not None else ABSENT_RANK_PENALTY
            for s in signals
        ]
        avg_rank = statistics.mean(ranks) if ranks else ABSENT_RANK_PENALTY
        rank_score = 1.0 - min(avg_rank - 1, MAX_RANK - 1) / (MAX_RANK - 1)
        rank_score = max(0.0, min(1.0, rank_score))

        # --- mention_rate ---
        mentioned = sum(1 for s in signals if s.mention_type != "absent")
        mention_rate = mentioned / total_probes

        # --- demand normalized ---
        search_volume_normalized = 0.0
        if demand and demand.search_volume is not None:
            search_volume_normalized = demand.search_volume / 100.0

        # --- alignment score ---
        alignment_score = (
            search_volume_normalized * 0.4 + rank_score * 0.4 + mention_rate * 0.2
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
        if len(ranks) <= 1:
            stability = 1.0
        else:
            rank_range = max(ranks) - min(ranks)
            stability = 1.0 - (rank_range / float(MAX_RANK))
            stability = max(0.0, min(1.0, stability))
        stability = round(stability, 4)

        # --- mention type distribution ---
        mention_dist = {}
        for sig in signals:
            mention_dist[sig.mention_type] = mention_dist.get(sig.mention_type, 0) + 1

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
            average_recommendation_rank=None,
            mention_type_distribution_json="{}",
            probes_included=0,
        )
