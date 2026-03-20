from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict


@dataclass
class DemandResult:
    entity_name: str
    search_volume: Optional[float]        # 0-100 (pytrends relative)
    trend_velocity: Optional[float]       # signed 30-day delta
    related_queries: List[str] = field(default_factory=list)
    geographic_distribution: Dict[str, float] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class CitationResult:
    cited_url: str
    domain: str
    content_type: Optional[str] = None
    entity_mention_count: Optional[int] = None
    page_recency: Optional[str] = None  # ISO datetime string if found
    error: Optional[str] = None


class BaseCollector(ABC):
    """Abstract base for all signal collectors."""

    collector_name: str  # class-level constant

    def __init__(self, settings):
        self.settings = settings

    @abstractmethod
    def collect(self, *args, **kwargs):
        """Execute collection. Return type varies by subclass."""
        ...
