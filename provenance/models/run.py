from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class RunStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class RunMode(str, Enum):
    isolation = "isolation"
    aggregate = "aggregate"


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


class RunCreate(SQLModel):
    entity_id: int
    mode: RunMode = RunMode.isolation
    experiment_id: Optional[int] = None


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
