from datetime import datetime
from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


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


class QueryProbeRead(SQLModel):
    id: int
    run_id: int
    query_variant: str
    query_text: str
    raw_response: str
    probed_at: datetime
    country: str
    region: Optional[str]
    language: str
    locale: str
    user_persona: Optional[str]
    expertise_level: Optional[str]
    stated_use_case: Optional[str]
    provider: str
    model: str
    temperature: float
    system_prompt_variant: Optional[str]
    prior_context: Optional[str]


def query_probe_to_read(probe: QueryProbe) -> QueryProbeRead:
    return QueryProbeRead(
        id=probe.id,
        run_id=probe.run_id,
        query_variant=probe.query_variant,
        query_text=probe.query_text,
        raw_response=probe.raw_response,
        probed_at=probe.probed_at,
        country=probe.country,
        region=probe.region,
        language=probe.language,
        locale=probe.locale,
        user_persona=probe.user_persona,
        expertise_level=probe.expertise_level,
        stated_use_case=probe.stated_use_case,
        provider=probe.provider,
        model=probe.model,
        temperature=probe.temperature,
        system_prompt_variant=probe.system_prompt_variant,
        prior_context=probe.prior_context,
    )
