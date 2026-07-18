"""
core/experiment_analysis.py — Experiment analytics: cross-run comparison and
drift tracking over an experiment's runs.

Read-time derivation only, per CLAUDE.md's flat-schema/late-derivation rule —
every method here queries existing Run/DivergenceScore rows and computes
results on the fly; nothing is written and no schema changes.
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional

from pydantic import BaseModel
from sqlmodel import Session, select

from provenance.models.divergence_score import DivergenceScore
from provenance.models.experiment import Experiment
from provenance.models.run import Run, RunStatus

NUMERIC_DELTA_METRICS = [
    "demand_llm_alignment_score",
    "cross_query_stability",
    "average_recommendation_rank",
]


class ExperimentNotFoundError(Exception):
    """Raised when an experiment_id does not exist."""


class RunSnapshot(BaseModel):
    run_id: int
    entity_id: int
    status: RunStatus
    completed_at: Optional[str] = None
    demand_llm_alignment_score: Optional[float] = None
    divergence_direction: Optional[str] = None
    cross_query_stability: Optional[float] = None
    average_recommendation_rank: Optional[float] = None
    mention_type_distribution: Dict[str, int] = {}
    probes_included: Optional[int] = None


class MetricDelta(BaseModel):
    metric: str
    first: float
    last: float
    delta: float


class ExperimentComparison(BaseModel):
    experiment_id: int
    name: str
    snapshots: List[RunSnapshot] = []
    deltas: List[MetricDelta] = []


class DriftPoint(BaseModel):
    completed_at: str
    run_id: int
    demand_llm_alignment_score: float
    average_recommendation_rank: Optional[float] = None
    cross_query_stability: float


class ExperimentDrift(BaseModel):
    experiment_id: int
    series: Dict[int, List[DriftPoint]] = {}


class ExperimentAnalyzer:
    """Read-time cross-run comparison and drift tracking for an experiment."""

    def __init__(self, session: Session):
        self.session = session

    def compare(self, experiment_id: int) -> ExperimentComparison:
        experiment = self._get_experiment_or_raise(experiment_id)
        runs = self._runs_for_experiment(experiment_id)

        snapshots = [self._snapshot_for_run(run) for run in runs]

        scored = [s for s in snapshots if s.demand_llm_alignment_score is not None]
        deltas: List[MetricDelta] = []
        if len(scored) >= 2:
            first, last = scored[0], scored[-1]
            for metric in NUMERIC_DELTA_METRICS:
                first_val = getattr(first, metric)
                last_val = getattr(last, metric)
                if first_val is None or last_val is None:
                    continue
                deltas.append(
                    MetricDelta(
                        metric=metric,
                        first=first_val,
                        last=last_val,
                        delta=round(last_val - first_val, 4),
                    )
                )

        return ExperimentComparison(
            experiment_id=experiment_id,
            name=experiment.name,
            snapshots=snapshots,
            deltas=deltas,
        )

    def drift(self, experiment_id: int) -> ExperimentDrift:
        self._get_experiment_or_raise(experiment_id)
        runs = self._runs_for_experiment(experiment_id)

        series: Dict[int, List[DriftPoint]] = {}
        for run in runs:
            if run.status != RunStatus.completed or run.completed_at is None:
                continue
            score = self._score_for_run(run.id)
            if score is None:
                continue
            series.setdefault(run.entity_id, []).append(
                DriftPoint(
                    completed_at=run.completed_at.isoformat(),
                    run_id=run.id,
                    demand_llm_alignment_score=score.demand_llm_alignment_score,
                    average_recommendation_rank=score.average_recommendation_rank,
                    cross_query_stability=score.cross_query_stability,
                )
            )

        return ExperimentDrift(experiment_id=experiment_id, series=series)

    def _get_experiment_or_raise(self, experiment_id: int) -> Experiment:
        experiment = self.session.get(Experiment, experiment_id)
        if experiment is None:
            raise ExperimentNotFoundError(f"Experiment {experiment_id} not found")
        return experiment

    def _runs_for_experiment(self, experiment_id: int) -> List[Run]:
        # Runs without a completed_at (pending/failed) sort after completed ones —
        # a comparison timeline reads best with unresolved runs trailing.
        return self.session.exec(
            select(Run)
            .where(Run.experiment_id == experiment_id)
            .order_by(Run.completed_at.asc().nullslast(), Run.id)
        ).all()

    def _score_for_run(self, run_id: int) -> Optional[DivergenceScore]:
        return self.session.exec(
            select(DivergenceScore).where(DivergenceScore.run_id == run_id)
        ).first()

    def _snapshot_for_run(self, run: Run) -> RunSnapshot:
        score = self._score_for_run(run.id) if run.status == RunStatus.completed else None
        return RunSnapshot(
            run_id=run.id,
            entity_id=run.entity_id,
            status=run.status,
            completed_at=run.completed_at.isoformat() if run.completed_at else None,
            demand_llm_alignment_score=score.demand_llm_alignment_score if score else None,
            divergence_direction=score.divergence_direction if score else None,
            cross_query_stability=score.cross_query_stability if score else None,
            average_recommendation_rank=score.average_recommendation_rank if score else None,
            mention_type_distribution=(
                json.loads(score.mention_type_distribution_json) if score else {}
            ),
            probes_included=score.probes_included if score else None,
        )
