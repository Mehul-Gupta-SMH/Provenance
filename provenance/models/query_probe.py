from sqlmodel import SQLModel, Field
from sqlalchemy import Index
from typing import Optional
from datetime import datetime


class QueryProbe(SQLModel, table=True):
    __tablename__ = "query_probe"
    # Composite index for the primary read pattern: all probes for a run, filtered by variant
    __table_args__ = (
        Index("ix_query_probe_run_variant", "run_id", "query_variant"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    # Run linkage
    run_id: int = Field(foreign_key="run.id", index=True)

    # Query context
    query_variant: str   # "direct" | "comparative" | "expert" | "contrarian"
    perturbation_index: int = 0  # 0 = canonical; 1+ = surface rephrasing for variance study
    query_text: str
    raw_response: str = ""

    # Temporal context — stored raw, all bucketing is read-time
    probed_at: datetime = Field(default_factory=datetime.utcnow)

    # Geographic context
    country: str = "US"
    region: Optional[str] = None
    language: str = "en"
    locale: str = "en-US"

    # User context
    user_persona: Optional[str] = None
    expertise_level: Optional[str] = None
    stated_use_case: Optional[str] = None

    # LLM context
    provider: str = ""
    model: str = ""
    temperature: float = 0.2
    system_prompt_variant: Optional[str] = None
    prior_context: Optional[str] = None  # JSON string of conversation history
