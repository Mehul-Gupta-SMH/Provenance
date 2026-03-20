from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class QueryProbe(SQLModel, table=True):
    __tablename__ = "query_probe"
    id: Optional[int] = Field(default=None, primary_key=True)

    # Run linkage
    run_id: int = Field(foreign_key="run.id", index=True)

    # Query context
    query_variant: str   # "direct" | "comparative" | "expert" | "contrarian"
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
