from sqlmodel import SQLModel, Field
from sqlalchemy import Index
from typing import Optional


class LLMSignal(SQLModel, table=True):
    __tablename__ = "llm_signal"
    # Composite index for the primary read pattern: all signals for a probe, filtered by mention type
    __table_args__ = (
        Index("ix_llm_signal_entry_mention", "entry_id", "mention_type"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    # entry_id is the universal join key — references query_probe.id (the atomic observation)
    # entity is reachable via: entry_id → query_probe.run_id → run.entity_id
    entry_id: int = Field(foreign_key="query_probe.id", index=True)

    # Recommendation signals
    recommendation_rank: Optional[int] = None   # 1-based; None = absent
    mention_type: str = "absent"                 # "primary" | "alternative" | "cautionary" | "absent"
    phrasing_sentiment: Optional[str] = None    # "positive" | "neutral" | "qualified"
    context_of_mention: Optional[str] = None

    # Co-mention signals — JSON string (list of entity name strings); v1/SQLite intentional
    co_mentioned_entities_json: str = Field(default="[]")

    # Stability (computed per-entity across variants in a run, stored for query convenience)
    query_sensitivity: Optional[float] = None   # 0-1
