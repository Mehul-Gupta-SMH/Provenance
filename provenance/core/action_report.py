"""
core/action_report.py — Action Report layer: read-time synthesis over signals
already stored, answering "what would it take to change the LLM's recommendation?"
for one run (thesis/thesis_20260315.md, "actionable" framing).

No writes. No new tables. Built on top of signal_service (the established
per-run read boundary) and the cached DivergenceScore row (itself always
re-derivable via DivergenceEngine — see core/divergence.py). Mirrors the
Pydantic-result + engine-class + rule-based idiom of core/analysis.py
(EntityFingerprint / FingerprintBuilder / GapItem / action_hint).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Union

from pydantic import BaseModel
from sqlmodel import Session, select

from provenance.models.divergence_score import DivergenceScore
from provenance.models.entity import Entity, matches_entity
from provenance.models.run import Run
from provenance.services import signal_service
from provenance.services.signal_service import RunNotFoundError

__all__ = ["Lever", "CompetitorPressure", "ActionReport", "ActionReportBuilder", "RunNotFoundError"]

_COMPARISON_CONTENT_TYPES = {"comparison", "docs"}
_LOW_HN_POINTS_THRESHOLD = 50


class Lever(BaseModel):
    title: str
    category: str  # "content" | "social" | "positioning" | "demand"
    rationale: str
    priority_score: float
    evidence: Dict[str, Union[float, str]]


class CompetitorPressure(BaseModel):
    name: str
    times_co_mentioned: int


class ActionReport(BaseModel):
    run_id: int
    entity_id: int
    entity_name: str
    headline: str
    alignment_score: Optional[float] = None
    divergence_direction: Optional[str] = None
    summary: str
    levers: List[Lever] = []
    competitor_pressure: List[CompetitorPressure] = []
    signals_considered: Dict[str, Union[float, str, None]] = {}


class ActionReportBuilder:
    """Assembles an ActionReport for a run from already-collected signals."""

    def __init__(self, session: Session):
        self.session = session

    def build(self, run_id: int) -> ActionReport:
        run = self.session.get(Run, run_id)
        if run is None:
            raise RunNotFoundError(f"Run {run_id} not found")
        entity = self.session.get(Entity, run.entity_id)

        signals = signal_service.list_signals_for_run(run_id, self.session)
        citations = signal_service.list_citations_for_run(run_id, self.session)
        demand_list = signal_service.list_demand_for_run(run_id, self.session)
        demand = demand_list[0] if demand_list else None
        social_points = signal_service.list_datapoints_for_run(
            run_id, self.session, signal_family="social"
        )
        divergence = self.session.exec(
            select(DivergenceScore)
            .where(DivergenceScore.run_id == run_id)
            .order_by(DivergenceScore.computed_at.desc())
        ).first()

        probes_included = divergence.probes_included if divergence else len(signals)
        mention_rate = (
            sum(1 for s in signals if s.mention_type != "absent") / probes_included
            if probes_included
            else 0.0
        )
        citation_count = len(citations)
        comparison_citation_count = sum(
            1 for c in citations if c.content_type in _COMPARISON_CONTENT_TYPES
        )
        hn_by_key = {p.signal_key: p.signal_value for p in social_points}
        hn_story_count = hn_by_key.get("hn_story_count", 0.0) or 0.0
        hn_points_total = hn_by_key.get("hn_points_total", 0.0) or 0.0

        # No divergence row and/or no signals means there is nothing to assess —
        # report None alignment fields rather than a stale/empty-score row's values.
        if divergence is not None and probes_included > 0:
            alignment_score = divergence.demand_llm_alignment_score
            divergence_direction = divergence.divergence_direction
            avg_rank = divergence.average_recommendation_rank
        else:
            alignment_score = None
            divergence_direction = None
            avg_rank = None

        signals_considered: Dict[str, Union[float, str, None]] = {
            "search_volume": demand.search_volume if demand else None,
            "trend_velocity": demand.trend_velocity if demand else None,
            "avg_recommendation_rank": avg_rank,
            "mention_rate": round(mention_rate, 4),
            "hn_story_count": hn_story_count,
            "hn_points_total": hn_points_total,
            "citation_count": citation_count,
            "comparison_citation_count": comparison_citation_count,
        }

        # No probe activity at all (no divergence row and no signals) means there is
        # nothing to base a recommendation on — every lever rule below assumes at
        # least one probe ran, so skip lever synthesis entirely.
        levers = (
            self._build_levers(
                demand=demand,
                probes_included=probes_included,
                citation_count=citation_count,
                comparison_citation_count=comparison_citation_count,
                hn_story_count=hn_story_count,
                hn_points_total=hn_points_total,
                mention_rate=mention_rate,
                avg_rank=avg_rank,
                alignment_score=alignment_score,
                divergence_direction=divergence_direction,
            )
            if probes_included > 0
            else []
        )
        levers.sort(key=lambda lever: lever.priority_score, reverse=True)

        competitor_pressure = self._build_competitor_pressure(signals, entity)

        headline = self._headline(divergence_direction, alignment_score)
        summary = self._summary(headline, levers)

        return ActionReport(
            run_id=run_id,
            entity_id=run.entity_id,
            entity_name=entity.name if entity else "",
            headline=headline,
            alignment_score=alignment_score,
            divergence_direction=divergence_direction,
            summary=summary,
            levers=levers,
            competitor_pressure=competitor_pressure,
            signals_considered=signals_considered,
        )

    def _build_levers(
        self,
        *,
        demand,
        probes_included: int,
        citation_count: int,
        comparison_citation_count: int,
        hn_story_count: float,
        hn_points_total: float,
        mention_rate: float,
        avg_rank: Optional[float],
        alignment_score: Optional[float],
        divergence_direction: Optional[str],
    ) -> List[Lever]:
        levers: List[Lever] = []

        # Content/evidence deficit
        if comparison_citation_count == 0 or citation_count < probes_included:
            high_demand = bool(demand and demand.search_volume and demand.search_volume >= 50)
            levers.append(
                Lever(
                    title="Publish comparison & documentation content",
                    category="content",
                    rationale=(
                        f"Only {comparison_citation_count} comparison/docs citation(s) and "
                        f"{citation_count} total citation(s) were observed across "
                        f"{probes_included} probe(s); LLMs disproportionately cite "
                        "comparison and documentation page types when recommending."
                    ),
                    priority_score=0.9 if high_demand else 0.6,
                    evidence={
                        "comparison_citation_count": comparison_citation_count,
                        "citation_count": citation_count,
                        "probes_included": probes_included,
                    },
                )
            )

        # Social proof deficit
        if hn_story_count == 0 or hn_points_total < _LOW_HN_POINTS_THRESHOLD:
            levers.append(
                Lever(
                    title="Build social proof and community discussion",
                    category="social",
                    rationale=(
                        f"Hacker News coverage is thin: {int(hn_story_count)} stor"
                        f"{'y' if hn_story_count == 1 else 'ies'} and "
                        f"{int(hn_points_total)} total points, below the "
                        f"{_LOW_HN_POINTS_THRESHOLD}-point social-proof threshold."
                    ),
                    priority_score=0.7,
                    evidence={
                        "hn_story_count": hn_story_count,
                        "hn_points_total": hn_points_total,
                    },
                )
            )

        # Positioning / absence
        if mention_rate < 0.5 or avg_rank is None or avg_rank > 3:
            rank_desc = (
                "no ranked mentions" if avg_rank is None else f"an average rank of {avg_rank}"
            )
            levers.append(
                Lever(
                    title="Establish stronger positioning to earn LLM mentions",
                    category="positioning",
                    rationale=(
                        f"The entity was mentioned in only {round(mention_rate * 100, 1)}% of "
                        f"probes, with {rank_desc}."
                    ),
                    priority_score=0.8,
                    evidence={
                        "mention_rate": round(mention_rate, 4),
                        "average_recommendation_rank": avg_rank,
                    },
                )
            )

        # Demand capture
        if divergence_direction == "demand_ahead":
            levers.append(
                Lever(
                    title="Capture existing demand into LLM visibility",
                    category="demand",
                    rationale=(
                        f"Alignment score is {alignment_score}, and measured real-world demand "
                        "outstrips the entity's current LLM standing — search interest "
                        "is not yet translating into recommendations."
                    ),
                    priority_score=0.85,
                    evidence={
                        "alignment_score": alignment_score,
                        "divergence_direction": divergence_direction,
                        "search_volume": demand.search_volume if demand else None,
                    },
                )
            )

        return levers

    def _build_competitor_pressure(
        self, signals, entity: Optional[Entity]
    ) -> List[CompetitorPressure]:
        counts: Dict[str, int] = {}
        display_names: Dict[str, str] = {}
        for signal in signals:
            for co_name in signal.co_mentioned_entities:
                key = co_name.strip().lower()
                if not key or (entity is not None and matches_entity(co_name, entity)):
                    continue
                counts[key] = counts.get(key, 0) + 1
                display_names.setdefault(key, co_name)

        ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:5]
        return [
            CompetitorPressure(name=display_names[key], times_co_mentioned=count)
            for key, count in ranked
        ]

    def _headline(
        self, divergence_direction: Optional[str], alignment_score: Optional[float]
    ) -> str:
        if divergence_direction is None or alignment_score is None:
            return "Insufficient probe signal to assess"
        if divergence_direction == "demand_ahead":
            return "Strong real-world demand, under-recommended by the LLM"
        if divergence_direction == "llm_ahead":
            return "LLM over-indexes relative to measured demand"
        return "LLM recommendation is aligned with demand"

    def _summary(self, headline: str, levers: List[Lever]) -> str:
        if not levers:
            return f"{headline}. No priority levers identified — current signal profile is healthy."
        top = levers[:2]
        titles = " and ".join(lever.title.lower() for lever in top)
        return f"{headline}. Highest-priority action: {titles}."
