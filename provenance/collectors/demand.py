"""
Demand signal collector via pytrends — functional implementation (v1).
Full implementation added in Phase 4.
"""
from provenance.collectors.base import BaseCollector, DemandResult


class DemandCollector(BaseCollector):
    collector_name = "demand"

    def collect(self, entity_name: str, category: str) -> DemandResult:
        raise NotImplementedError("DemandCollector.collect() — implemented in Phase 4")
