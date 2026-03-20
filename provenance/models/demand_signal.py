from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class DemandSignal(SQLModel, table=True):
    __tablename__ = "demand_signal"
    id: Optional[int] = Field(default=None, primary_key=True)

    entity_id: int = Field(foreign_key="entity.id", index=True)
    run_id: int = Field(foreign_key="run.id", index=True)
    collected_at: datetime = Field(default_factory=datetime.utcnow)

    # Raw demand signals — all flat, no bucketing at write time
    search_volume: Optional[float] = None           # 0-100 (pytrends relative)
    trend_velocity: Optional[float] = None          # signed 30-day delta
    related_queries_json: str = Field(default="[]")         # JSON: top 5 rising queries
    geographic_distribution_json: str = Field(default="{}")  # JSON: {region: score}
