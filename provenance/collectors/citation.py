"""
Citation extractor — functional implementation (v1).
Full implementation added in Phase 4.
"""
from provenance.collectors.base import BaseCollector, CitationResult
from typing import List


class CitationExtractor(BaseCollector):
    collector_name = "citation"

    def collect(self, raw_response: str, entity_name: str) -> List[CitationResult]:
        raise NotImplementedError("CitationExtractor.collect() — implemented in Phase 4")
