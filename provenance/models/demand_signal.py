import json
from datetime import datetime
from typing import Dict, List, Optional

from sqlmodel import Field, SQLModel


class DemandSignal(SQLModel, table=True):
    __tablename__ = "demand_signal"
    id: Optional[int] = Field(default=None, primary_key=True)

    # entity is reachable via: run_id → run.entity_id
    run_id: int = Field(foreign_key="run.id", index=True)
    collected_at: datetime = Field(default_factory=datetime.utcnow)

    # Raw demand signals — all flat, no bucketing at write time
    search_volume: Optional[float] = None   # 0-100 (pytrends relative)
    trend_velocity: Optional[float] = None  # signed 30-day delta
    # JSON string (top 5 rising queries); v1/SQLite intentional
    related_queries_json: str = Field(default="[]")
    # JSON string ({region: score}); v1/SQLite intentional
    geographic_distribution_json: str = Field(default="{}")


class DemandSignalRead(SQLModel):
    id: int
    run_id: int
    collected_at: datetime
    search_volume: Optional[float]
    trend_velocity: Optional[float]
    related_queries: List[str]
    geographic_distribution: Dict[str, float]


def demand_signal_to_read(signal: DemandSignal) -> DemandSignalRead:
    return DemandSignalRead(
        id=signal.id,
        run_id=signal.run_id,
        collected_at=signal.collected_at,
        search_volume=signal.search_volume,
        trend_velocity=signal.trend_velocity,
        related_queries=json.loads(signal.related_queries_json),
        geographic_distribution=json.loads(signal.geographic_distribution_json),
    )
