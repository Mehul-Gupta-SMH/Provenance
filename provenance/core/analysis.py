"""
core/analysis.py — Phase 7 Analysis Layer (PLAN.md section 11).

FingerprintBuilder assembles a read-time EntityFingerprint from a completed run's
raw QueryProbe/LLMSignal/DemandSignal rows plus the cached DivergenceScore row
(itself always re-derivable via DivergenceEngine — see core/divergence.py).
CompetitorDelta diffs two fingerprints field-by-field. GapAnalyzer prioritizes
the resulting gaps by estimated impact on alignment_score.

Reconciled queries per PLAN.md v1.1 delta #2: LLMSignal carries no entity_id —
every signal for a run's probes describes that run's own entity by construction,
so signals are fetched via `entry_id.in_(...)` with no entity filter. DemandSignal
is filtered by run_id only (it carries no entity_id column either).
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional

from pydantic import BaseModel
from sqlmodel import Session, select

from provenance.models.demand_signal import DemandSignal
from provenance.models.divergence_score import DivergenceScore
from provenance.models.entity import Entity
from provenance.models.llm_signal import LLMSignal
from provenance.models.query_probe import QueryProbe
from provenance.models.run import Run, RunStatus


class EntityNotFoundError(Exception):
    """Raised when a fingerprint is requested for an entity_id that does not exist."""


class NoCompletedRunError(Exception):
    """Raised when no completed run is available to build a fingerprint from (either
    no completed run exists for the entity, or a given run_id is not a completed
    run belonging to that entity)."""


class EntityFingerprint(BaseModel):
    entity_id: int
    entity_name: str
    run_id: int

    # Demand signals
    search_volume: Optional[float] = None
    trend_velocity: Optional[float] = None
    related_queries: List[str] = []
    geographic_distribution: Dict[str, float] = {}

    # LLM signals (aggregated across probes for this run)
    average_recommendation_rank: Optional[float] = None  # lower = better
    mention_rate: float = 0.0
    primary_mention_rate: float = 0.0
    phrasing_sentiment_distribution: Dict[str, float] = {}
    top_co_mentioned: List[str] = []
    cross_query_stability: float = 0.0

    # Divergence
    alignment_score: float = 0.0
    divergence_direction: str = "demand_ahead"


class FingerprintBuilder:
    """Assembles an EntityFingerprint for an entity's latest-or-specified completed run."""

    def __init__(self, session: Session):
        self.session = session

    def build(self, entity_id: int, run_id: Optional[int] = None) -> EntityFingerprint:
        entity = self.session.get(Entity, entity_id)
        if entity is None:
            raise EntityNotFoundError(f"Entity {entity_id} not found")

        run = self._resolve_run(entity_id, run_id)

        demand = self.session.exec(
            select(DemandSignal).where(DemandSignal.run_id == run.id)
        ).first()
        divergence = self.session.exec(
            select(DivergenceScore)
            .where(DivergenceScore.entity_id == entity_id)
            .where(DivergenceScore.run_id == run.id)
        ).first()
        probes = self.session.exec(select(QueryProbe).where(QueryProbe.run_id == run.id)).all()
        entry_ids = [p.id for p in probes]
        # No entity filter: every signal in this run describes the run's own entity.
        signals = (
            self.session.exec(
                select(LLMSignal).where(LLMSignal.entry_id.in_(entry_ids))
            ).all()
            if entry_ids
            else []
        )

        ranks = [s.recommendation_rank for s in signals if s.recommendation_rank]
        avg_rank = sum(ranks) / len(ranks) if ranks else None
        mention_rate = (
            sum(1 for s in signals if s.mention_type != "absent") / len(probes) if probes else 0.0
        )
        primary_rate = (
            sum(1 for s in signals if s.mention_type == "primary") / len(probes) if probes else 0.0
        )

        sentiment_dist: Dict[str, int] = {}
        co_mention_counts: Dict[str, int] = {}
        for sig in signals:
            if sig.phrasing_sentiment:
                sentiment_dist[sig.phrasing_sentiment] = (
                    sentiment_dist.get(sig.phrasing_sentiment, 0) + 1
                )
            for co in json.loads(sig.co_mentioned_entities_json or "[]"):
                co_mention_counts[co] = co_mention_counts.get(co, 0) + 1

        total_signals = len(signals) or 1
        sentiment_pct = {k: round(v / total_signals, 3) for k, v in sentiment_dist.items()}
        top_co = sorted(co_mention_counts, key=co_mention_counts.get, reverse=True)[:5]

        return EntityFingerprint(
            entity_id=entity_id,
            entity_name=entity.name,
            run_id=run.id,
            search_volume=demand.search_volume if demand else None,
            trend_velocity=demand.trend_velocity if demand else None,
            related_queries=json.loads(demand.related_queries_json) if demand else [],
            geographic_distribution=(
                json.loads(demand.geographic_distribution_json) if demand else {}
            ),
            average_recommendation_rank=avg_rank,
            mention_rate=mention_rate,
            primary_mention_rate=primary_rate,
            phrasing_sentiment_distribution=sentiment_pct,
            top_co_mentioned=top_co,
            cross_query_stability=divergence.cross_query_stability if divergence else 0.0,
            alignment_score=divergence.demand_llm_alignment_score if divergence else 0.0,
            divergence_direction=divergence.divergence_direction if divergence else "demand_ahead",
        )

    def _resolve_run(self, entity_id: int, run_id: Optional[int]) -> Run:
        if run_id is not None:
            run = self.session.get(Run, run_id)
            if run is None or run.entity_id != entity_id or run.status != RunStatus.completed:
                raise NoCompletedRunError(
                    f"Run {run_id} is not a completed run for entity {entity_id}"
                )
            return run

        run = self.session.exec(
            select(Run)
            .where(Run.entity_id == entity_id)
            .where(Run.status == RunStatus.completed)
            .order_by(Run.completed_at.desc())
        ).first()
        if run is None:
            raise NoCompletedRunError(f"No completed run found for entity {entity_id}")
        return run


# ---------------------------------------------------------------------------
# Competitor Delta
# ---------------------------------------------------------------------------

NUMERIC_FIELDS = [
    "search_volume",
    "trend_velocity",
    "average_recommendation_rank",
    "mention_rate",
    "primary_mention_rate",
    "cross_query_stability",
    "alignment_score",
]
# recommendation_rank is inverted — lower is better
INVERTED_FIELDS = {"average_recommendation_rank"}


class FieldDelta(BaseModel):
    field: str
    entity_value: Optional[float]
    competitor_value: Optional[float]
    delta: Optional[float]  # entity - competitor
    direction: str  # "entity_leads" | "competitor_leads" | "parity"


class CompetitorDeltaResult(BaseModel):
    entity_id: int
    competitor_entity_id: int
    entity_run_id: int
    competitor_run_id: int
    deltas: List[FieldDelta]
    summary_advantage_fields: List[str]  # fields where entity_leads
    summary_gap_fields: List[str]  # fields where competitor_leads


class CompetitorDelta:
    """Diffs two entity fingerprints field-by-field."""

    def compute(
        self, entity_fp: EntityFingerprint, competitor_fp: EntityFingerprint
    ) -> CompetitorDeltaResult:
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
                # Lower rank = better, so the advantage interpretation is inverted.
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

            deltas.append(
                FieldDelta(
                    field=field,
                    entity_value=ev_f,
                    competitor_value=cv_f,
                    delta=round(raw_delta, 4),
                    direction=direction,
                )
            )

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


# ---------------------------------------------------------------------------
# Gap Analysis
# ---------------------------------------------------------------------------

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

ACTION_HINTS = {
    "average_recommendation_rank": (
        "Improve LLM rank through authoritative content and citation signals"
    ),
    "mention_rate": "Increase entity visibility in LLM responses via broader content coverage",
    "primary_mention_rate": (
        "Position entity as primary recommendation through use-case specificity"
    ),
    "alignment_score": (
        "Align demand signals with LLM behavior through content and authority building"
    ),
    "cross_query_stability": (
        "Improve consistency across query framings via clear entity positioning"
    ),
    "search_volume": "Increase search demand through SEO and brand awareness efforts",
    "trend_velocity": "Drive trend momentum through launches, publications, and community presence",
}


class GapItem(BaseModel):
    field: str
    entity_value: Optional[float]
    competitor_value: Optional[float]
    gap_magnitude: float  # abs(delta)
    impact_weight: float
    priority_score: float  # gap_magnitude * impact_weight
    action_hint: str


class GapAnalyzer:
    """Prioritizes competitor-delta gaps by estimated impact on alignment_score."""

    def analyze(self, delta_result: CompetitorDeltaResult) -> List[GapItem]:
        gaps = []
        for d in delta_result.deltas:
            if d.direction != "competitor_leads":
                continue
            magnitude = abs(d.delta) if d.delta is not None else 0.0
            weight = FIELD_IMPACT_WEIGHTS.get(d.field, 0.1)
            priority = round(magnitude * weight, 4)
            gaps.append(
                GapItem(
                    field=d.field,
                    entity_value=d.entity_value,
                    competitor_value=d.competitor_value,
                    gap_magnitude=round(magnitude, 4),
                    impact_weight=weight,
                    priority_score=priority,
                    action_hint=ACTION_HINTS.get(d.field, "Investigate this signal gap"),
                )
            )

        gaps.sort(key=lambda g: g.priority_score, reverse=True)
        return gaps
