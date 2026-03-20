from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class DivergenceScore(SQLModel, table=True):
    __tablename__ = "divergence_score"
    id: Optional[int] = Field(default=None, primary_key=True)

    run_id: int = Field(foreign_key="run.id", index=True)
    entity_id: int = Field(foreign_key="entity.id", index=True)
    computed_at: datetime = Field(default_factory=datetime.utcnow)

    # Core divergence signals
    demand_llm_alignment_score: float = 0.0      # 0.0 to 1.0
    divergence_direction: str = "aligned"         # "llm_ahead" | "demand_ahead" | "aligned"
    cross_query_stability: float = 0.0            # 0.0 to 1.0

    # Supporting detail
    average_recommendation_rank: Optional[float] = None
    mention_type_distribution_json: str = Field(default="{}")  # JSON: {type: count}
    probes_included: int = 0
