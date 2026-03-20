from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class Citation(SQLModel, table=True):
    __tablename__ = "citation"
    id: Optional[int] = Field(default=None, primary_key=True)

    probe_id: int = Field(foreign_key="query_probe.id", index=True)

    cited_url: str
    domain: str
    page_recency: Optional[datetime] = None
    content_type: Optional[str] = None          # "docs" | "blog" | "comparison" | "review" | "forum"
    entity_mention_count: Optional[int] = None
