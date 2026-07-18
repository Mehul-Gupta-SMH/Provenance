from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Citation(SQLModel, table=True):
    __tablename__ = "citation"
    id: Optional[int] = Field(default=None, primary_key=True)

    # entry_id is the universal join key — references query_probe.id (the atomic observation)
    entry_id: int = Field(foreign_key="query_probe.id", index=True)

    cited_url: str
    domain: str
    page_recency: Optional[datetime] = None
    content_type: Optional[str] = None  # "docs" | "blog" | "comparison" | "review" | "forum"
    entity_mention_count: Optional[int] = None


class CitationRead(SQLModel):
    id: int
    entry_id: int
    cited_url: str
    domain: str
    page_recency: Optional[datetime]
    content_type: Optional[str]
    entity_mention_count: Optional[int]


def citation_to_read(citation: Citation) -> CitationRead:
    return CitationRead(
        id=citation.id,
        entry_id=citation.entry_id,
        cited_url=citation.cited_url,
        domain=citation.domain,
        page_recency=citation.page_recency,
        content_type=citation.content_type,
        entity_mention_count=citation.entity_mention_count,
    )
