from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class DemandSignal(SQLModel, table=True):
    __tablename__ = "demand_signal"
    id: Optional[int] = Field(default=None, primary_key=True)

    # entity is reachable via: run_id → run.entity_id
    run_id: int = Field(foreign_key="run.id", index=True)
    collected_at: datetime = Field(default_factory=datetime.utcnow)

    # Raw demand signals — all flat, no bucketing at write time
    search_volume: Optional[float] = None           # 0-100 (pytrends relative)
    trend_velocity: Optional[float] = None          # signed 30-day delta
    related_queries_json: str = Field(default="[]")         # JSON string (top 5 rising queries); v1/SQLite intentional
    geographic_distribution_json: str = Field(default="{}")  # JSON string ({region: score}); v1/SQLite intentional
