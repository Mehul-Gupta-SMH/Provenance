from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class Experiment(SQLModel, table=True):
    """
    Groups runs under a named experiment.
    Enables cross-run comparison, drift tracking, and A/B analysis.
    Every Run belongs to an Experiment (nullable for backwards compat).

    Examples:
        "baseline-2026-Q1"
        "post-content-update-april"
        "competitor-benchmark-neo4j"
    """
    __tablename__ = "experiment"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    description: Optional[str] = None
    # Free-form config overrides for this experiment (probe settings, persona, etc.)
    config_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ExperimentCreate(SQLModel):
    name: str
    description: Optional[str] = None
    config_json: str = "{}"


class ExperimentRead(SQLModel):
    id: int
    name: str
    description: Optional[str]
    config_json: str
    created_at: datetime
