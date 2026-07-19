"""
core/citation_analytics.py — Citation-domain analytics: which domains an LLM
leans on when recommending in a category, aggregated at read time per run or
per experiment.

Read-time derivation only, per CLAUDE.md's flat-schema/late-derivation rule —
every method here queries existing Citation/QueryProbe/Run rows and computes
results on the fly; nothing is written and no schema changes.
"""
from __future__ import annotations

from collections import Counter
from typing import Dict, List

from pydantic import BaseModel
from sqlmodel import Session, select

from provenance.core.experiment_analysis import ExperimentNotFoundError
from provenance.models.citation import Citation
from provenance.models.experiment import Experiment
from provenance.models.query_probe import QueryProbe
from provenance.models.run import Run
from provenance.services.signal_service import RunNotFoundError

DEFAULT_TOP_N = 10


class DomainStat(BaseModel):
    domain: str
    citation_count: int
    content_type_distribution: Dict[str, int] = {}


class CitationAnalytics(BaseModel):
    scope: str  # "run" | "experiment"
    scope_id: int
    total_citations: int
    unique_domains: int
    top_domains: List[DomainStat] = []


class CitationAnalyticsEngine:
    """Read-time citation-domain aggregation for a run or an experiment."""

    def __init__(self, session: Session):
        self.session = session

    def for_run(self, run_id: int, top_n: int = DEFAULT_TOP_N) -> CitationAnalytics:
        if self.session.get(Run, run_id) is None:
            raise RunNotFoundError(f"Run {run_id} not found")
        probe_ids = self._probe_ids_for_runs([run_id])
        citations = self._citations_for_probe_ids(probe_ids)
        return self._build(scope="run", scope_id=run_id, citations=citations, top_n=top_n)

    def for_experiment(self, experiment_id: int, top_n: int = DEFAULT_TOP_N) -> CitationAnalytics:
        if self.session.get(Experiment, experiment_id) is None:
            raise ExperimentNotFoundError(f"Experiment {experiment_id} not found")
        run_ids = list(
            self.session.exec(select(Run.id).where(Run.experiment_id == experiment_id)).all()
        )
        probe_ids = self._probe_ids_for_runs(run_ids)
        citations = self._citations_for_probe_ids(probe_ids)
        return self._build(
            scope="experiment", scope_id=experiment_id, citations=citations, top_n=top_n
        )

    def _probe_ids_for_runs(self, run_ids: List[int]) -> List[int]:
        if not run_ids:
            return []
        return list(
            self.session.exec(select(QueryProbe.id).where(QueryProbe.run_id.in_(run_ids))).all()
        )

    def _citations_for_probe_ids(self, probe_ids: List[int]) -> List[Citation]:
        if not probe_ids:
            return []
        return list(
            self.session.exec(select(Citation).where(Citation.entry_id.in_(probe_ids))).all()
        )

    def _build(
        self, scope: str, scope_id: int, citations: List[Citation], top_n: int
    ) -> CitationAnalytics:
        domain_counts: Counter = Counter()
        content_type_counts: Dict[str, Counter] = {}
        for citation in citations:
            domain_counts[citation.domain] += 1
            content_type = citation.content_type or "unknown"
            content_type_counts.setdefault(citation.domain, Counter())[content_type] += 1

        top_domains = [
            DomainStat(
                domain=domain,
                citation_count=count,
                content_type_distribution=dict(content_type_counts[domain]),
            )
            for domain, count in sorted(domain_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ][:top_n]

        return CitationAnalytics(
            scope=scope,
            scope_id=scope_id,
            total_citations=len(citations),
            unique_domains=len(domain_counts),
            top_domains=top_domains,
        )
