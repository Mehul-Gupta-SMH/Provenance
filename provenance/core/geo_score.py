"""
core/geo_score.py — Composite 0-100 GEO score: read-time rollup of existing
signals into one trackable number with named, weighted sub-components and
discoverability bands (docs/roadmap.md, "Composite 0-100 GEO score", rank 2).

Read-time derivation only, per CLAUDE.md's flat-schema/late-derivation rule —
every value here is re-derived from DivergenceScore/DataPoint/Citation rows
already written by other engines/collectors; nothing is written and no schema
changes. Mirrors the Pydantic-result + engine-class idiom of
core/citation_analytics.py.

Weights (module-level constant for this wave, per the task's instruction not
to touch config.py, which another agent owns) and bands are taken verbatim
from docs/roadmap.md's discoverability rubric:
    excellent 86-100 * good 68-85 * foundation 36-67 * critical 0-35

Component derivation, each normalized to 0..1 (never raises on absent data —
an absent signal normalizes to 0.0 and its component name is recorded in
GeoScore.missing_signals):

    alignment       - latest DivergenceScore.demand_llm_alignment_score (already 0..1).
    stability       - latest DivergenceScore.cross_query_stability (already 0..1).
    visibility      - proxied via DivergenceScore.average_recommendation_rank:
                       rank 1 -> 1.0, rank >= MAX_RANK+1/absent -> 0.0. Position-
                       adjusted word count (docs/roadmap.md's PAWC) is a future,
                       richer visibility signal; this proxies via rank only.
    content_quality - blend of whichever GEO-paper-important content DataPoints
                       (signal_family="content") are present: statistics_density,
                       quotation_density, external_citation_density. Each raw
                       density is unbounded, so it is squashed via
                       min(value / _CONTENT_DENSITY_CAPS[key], 1.0) before
                       averaging across whichever keys the collector wrote.
    authority       - blend of social DataPoint hn_points_total
                       (signal_family="social") and citation density
                       (citation count / probe count), each squashed similarly.
"""
from __future__ import annotations

import statistics
from typing import Dict, List, Optional

from pydantic import BaseModel
from sqlmodel import Session, select

from provenance.models.divergence_score import DivergenceScore
from provenance.models.run import Run
from provenance.services import signal_service
from provenance.services.signal_service import RunNotFoundError

__all__ = ["GeoScoreComponent", "GeoScore", "GeoScoreEngine", "RunNotFoundError"]

# Sub-component weights - must sum to 1.0.
_WEIGHTS = {
    "visibility": 0.35,
    "alignment": 0.25,
    "content_quality": 0.20,
    "authority": 0.10,
    "stability": 0.10,
}

# Discoverability bands (docs/roadmap.md).
_BAND_THRESHOLDS = (
    (86, "excellent"),
    (68, "good"),
    (36, "foundation"),
)
_BAND_DEFAULT = "critical"

# Visibility-via-rank proxy (mirrors core/divergence.py's MAX_RANK convention).
MAX_RANK = 5

# Unbounded content-density raw values are squashed to 0..1 via value/cap,
# clamped at 1.0. Caps are deliberately generous documented guesses — a page
# hitting the cap is already saturating that signal.
_CONTENT_DENSITY_CAPS = {
    "statistics_density": 10.0,
    "quotation_density": 5.0,
    "external_citation_density": 10.0,
}
_HN_POINTS_CAP = 200.0


def _band(score: float) -> str:
    for threshold, name in _BAND_THRESHOLDS:
        if score >= threshold:
            return name
    return _BAND_DEFAULT


class GeoScoreComponent(BaseModel):
    name: str
    raw: Optional[float] = None
    normalized: float
    weight: float
    contribution: float


class GeoScore(BaseModel):
    run_id: int
    geo_score: float
    band: str
    components: List[GeoScoreComponent] = []
    missing_signals: List[str] = []


class GeoScoreEngine:
    """Read-time computation of the composite GEO score for a run."""

    def __init__(self, session: Session):
        self.session = session

    def compute(self, run_id: int) -> GeoScore:
        if self.session.get(Run, run_id) is None:
            raise RunNotFoundError(f"Run {run_id} not found")

        divergence = self.session.exec(
            select(DivergenceScore)
            .where(DivergenceScore.run_id == run_id)
            .order_by(DivergenceScore.computed_at.desc())
        ).first()
        probe_count = len(signal_service.list_probes_for_run(run_id, self.session))

        missing_signals: List[str] = []
        components: List[GeoScoreComponent] = []

        for name, (raw, normalized) in (
            ("alignment", self._alignment(divergence)),
            ("stability", self._stability(divergence)),
            ("visibility", self._visibility(divergence)),
            ("content_quality", self._content_quality(run_id)),
            ("authority", self._authority(run_id, probe_count)),
        ):
            if normalized is None:
                missing_signals.append(name)
                normalized = 0.0
            weight = _WEIGHTS[name]
            components.append(
                GeoScoreComponent(
                    name=name,
                    raw=raw,
                    normalized=normalized,
                    weight=weight,
                    contribution=normalized * weight * 100,
                )
            )

        total = sum(c.contribution for c in components)
        geo_score = round(max(0.0, min(100.0, total)), 2)

        return GeoScore(
            run_id=run_id,
            geo_score=geo_score,
            band=_band(geo_score),
            components=components,
            missing_signals=missing_signals,
        )

    def _alignment(self, divergence: Optional[DivergenceScore]):
        if divergence is None:
            return None, None
        value = divergence.demand_llm_alignment_score
        return value, value

    def _stability(self, divergence: Optional[DivergenceScore]):
        if divergence is None:
            return None, None
        value = divergence.cross_query_stability
        return value, value

    def _visibility(self, divergence: Optional[DivergenceScore]):
        if divergence is None or divergence.average_recommendation_rank is None:
            return None, None
        avg_rank = divergence.average_recommendation_rank
        normalized = max(0.0, min(1.0, (MAX_RANK - (avg_rank - 1)) / MAX_RANK))
        return avg_rank, normalized

    def _content_quality(self, run_id: int):
        content_points = signal_service.list_datapoints_for_run(
            run_id, self.session, signal_family="content"
        )
        by_key: Dict[str, float] = {
            p.signal_key: p.signal_value for p in content_points if p.signal_value is not None
        }
        squashed = [
            min(by_key[key] / cap, 1.0)
            for key, cap in _CONTENT_DENSITY_CAPS.items()
            if key in by_key
        ]
        if not squashed:
            return None, None
        return None, statistics.mean(squashed)

    def _authority(self, run_id: int, probe_count: int):
        social_points = signal_service.list_datapoints_for_run(
            run_id, self.session, signal_family="social"
        )
        by_key: Dict[str, float] = {
            p.signal_key: p.signal_value for p in social_points if p.signal_value is not None
        }
        citation_count = len(signal_service.list_citations_for_run(run_id, self.session))

        parts = []
        if "hn_points_total" in by_key:
            parts.append(min(by_key["hn_points_total"] / _HN_POINTS_CAP, 1.0))
        if probe_count > 0:
            parts.append(min(citation_count / probe_count, 1.0))

        if not parts:
            return None, None
        return None, statistics.mean(parts)
