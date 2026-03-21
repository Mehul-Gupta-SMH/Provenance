from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class DataPoint(SQLModel, table=True):
    """
    Ever-expanding signal store. The EAV layer for future signal families.

    Structured tables (LLMSignal, DemandSignal, Citation) exist for core signals
    that need typed columns and indexed access. DataPoint absorbs everything else —
    new signal collectors write here without any schema migration.

    Join key:
        - Per-probe signals:  entry_id (FK → query_probe.id)
        - Per-run signals:    run_id   (FK → run.id)
        - Per-entity signals: entity_id (FK → entity.id)

    Examples:
        signal_family="social",    signal_key="reddit_mention_count",  signal_value=42
        signal_family="authority", signal_key="domain_authority",      signal_value=67.3
        signal_family="semantic",  signal_key="embedding_similarity",  signal_value=0.87
        signal_family="social",    signal_key="hn_points",             signal_value=312
    """
    __tablename__ = "data_point"
    id: Optional[int] = Field(default=None, primary_key=True)

    # Join keys — at least one must be set
    entry_id: Optional[int] = Field(default=None, foreign_key="query_probe.id", index=True)
    run_id: Optional[int] = Field(default=None, foreign_key="run.id", index=True)
    entity_id: Optional[int] = Field(default=None, foreign_key="entity.id", index=True)
    experiment_id: Optional[int] = Field(default=None, foreign_key="experiment.id", index=True)

    # Signal identity
    signal_family: str = Field(index=True)   # "social" | "authority" | "semantic" | "content" | ...
    signal_key: str = Field(index=True)       # "reddit_mention_count" | "domain_authority" | ...

    # Signal value — numeric or text, never both null
    signal_value: Optional[float] = None
    signal_text: Optional[str] = None

    # Provenance of the data point itself
    collected_at: datetime = Field(default_factory=datetime.utcnow)
    collector_name: str = ""        # which collector produced this
    collector_version: str = "1.0"  # version for reproducibility tracking
