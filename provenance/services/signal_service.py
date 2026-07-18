"""Service layer for read-only per-run signal inspection (PLAN.md section 12).

Per PLAN.md v1.1 delta #2, LLMSignal/Citation carry no entity_id or run_id —
they join to a run through entry_id -> query_probe.id -> query_probe.run_id.
DemandSignal carries run_id directly. No aggregation here: rows are fetched
flat and deserialized via the *_to_read helpers, matching the entity_to_read
convention in models/entity.py.
"""

from typing import List, Optional

from sqlmodel import Session, select

from provenance.models.citation import Citation, CitationRead, citation_to_read
from provenance.models.data_point import DataPoint, DataPointRead, data_point_to_read
from provenance.models.demand_signal import (
    DemandSignal,
    DemandSignalRead,
    demand_signal_to_read,
)
from provenance.models.llm_signal import LLMSignal, LLMSignalRead, llm_signal_to_read
from provenance.models.query_probe import QueryProbe, QueryProbeRead, query_probe_to_read
from provenance.models.run import Run


class RunNotFoundError(Exception):
    """Raised when a signal-read function is called with a run_id that does not exist."""


def _require_run(run_id: int, session: Session) -> None:
    if session.get(Run, run_id) is None:
        raise RunNotFoundError(f"Run {run_id} not found")


def _probe_ids_for_run(run_id: int, session: Session) -> List[int]:
    return list(session.exec(select(QueryProbe.id).where(QueryProbe.run_id == run_id)).all())


def list_probes_for_run(run_id: int, session: Session) -> List[QueryProbeRead]:
    _require_run(run_id, session)
    probes = session.exec(select(QueryProbe).where(QueryProbe.run_id == run_id)).all()
    return [query_probe_to_read(p) for p in probes]


def list_signals_for_run(run_id: int, session: Session) -> List[LLMSignalRead]:
    _require_run(run_id, session)
    probe_ids = _probe_ids_for_run(run_id, session)
    if not probe_ids:
        return []
    signals = session.exec(select(LLMSignal).where(LLMSignal.entry_id.in_(probe_ids))).all()
    return [llm_signal_to_read(s) for s in signals]


def list_citations_for_run(run_id: int, session: Session) -> List[CitationRead]:
    _require_run(run_id, session)
    probe_ids = _probe_ids_for_run(run_id, session)
    if not probe_ids:
        return []
    citations = session.exec(select(Citation).where(Citation.entry_id.in_(probe_ids))).all()
    return [citation_to_read(c) for c in citations]


def list_demand_for_run(run_id: int, session: Session) -> List[DemandSignalRead]:
    _require_run(run_id, session)
    signals = session.exec(select(DemandSignal).where(DemandSignal.run_id == run_id)).all()
    return [demand_signal_to_read(s) for s in signals]


def list_datapoints_for_run(
    run_id: int, session: Session, signal_family: Optional[str] = None
) -> List[DataPointRead]:
    _require_run(run_id, session)
    query = select(DataPoint).where(DataPoint.run_id == run_id)
    if signal_family is not None:
        query = query.where(DataPoint.signal_family == signal_family)
    data_points = session.exec(query).all()
    return [data_point_to_read(d) for d in data_points]
