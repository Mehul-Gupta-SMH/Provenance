import json
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import field_validator
from sqlmodel import Field, SQLModel


class RunStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class RunMode(str, Enum):
    isolation = "isolation"
    aggregate = "aggregate"


class ProbeContextSpec(SQLModel):
    """One entry in a run's probe_contexts matrix. Mirrors ProbeContext (probes/base.py);
    all fields optional — unset fields fall back to ProbeContext's own defaults at
    pipeline execution time."""
    country: Optional[str] = None
    region: Optional[str] = None
    language: Optional[str] = None
    locale: Optional[str] = None
    user_persona: Optional[str] = None
    expertise_level: Optional[str] = None
    stated_use_case: Optional[str] = None
    temperature: Optional[float] = None
    system_prompt_variant: Optional[str] = None


MAX_PROBE_CONTEXTS = 10


class Run(SQLModel, table=True):
    __tablename__ = "run"
    id: Optional[int] = Field(default=None, primary_key=True)
    entity_id: int = Field(foreign_key="entity.id", index=True)
    # experiment_id groups runs for cross-run comparison and drift tracking
    experiment_id: Optional[int] = Field(default=None, foreign_key="experiment.id", index=True)
    mode: RunMode = RunMode.isolation
    status: RunStatus = RunStatus.pending
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # Stored ProbeContextSpec list (JSON); service layer serializes/deserializes.
    # Empty list means "today's single default context" (pipeline behavior unchanged).
    probe_contexts_json: str = Field(default="[]")


class RunCreate(SQLModel):
    entity_id: int
    mode: RunMode = RunMode.isolation
    experiment_id: Optional[int] = None
    probe_contexts: List[ProbeContextSpec] = []

    @field_validator("probe_contexts")
    @classmethod
    def _max_probe_contexts(cls, v: List[ProbeContextSpec]) -> List[ProbeContextSpec]:
        if len(v) > MAX_PROBE_CONTEXTS:
            raise ValueError(f"probe_contexts cannot exceed {MAX_PROBE_CONTEXTS} entries")
        return v


class RunRead(SQLModel):
    id: int
    entity_id: int
    experiment_id: Optional[int]
    mode: RunMode
    status: RunStatus
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    created_at: datetime
    # Default [] lets other routes' response_model=RunRead coercion keep working
    # on plain Run ORM objects (which have no `probe_contexts` attribute); routes
    # that need the deserialized list use run_to_read() below.
    probe_contexts: List[ProbeContextSpec] = []


def run_to_read(run: Run) -> RunRead:
    return RunRead(
        id=run.id,
        entity_id=run.entity_id,
        experiment_id=run.experiment_id,
        mode=run.mode,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        error_message=run.error_message,
        created_at=run.created_at,
        probe_contexts=[ProbeContextSpec(**c) for c in json.loads(run.probe_contexts_json)],
    )
