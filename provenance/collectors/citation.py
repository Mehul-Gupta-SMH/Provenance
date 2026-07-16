"""
Citation extractor — functional implementation (v1).

Pure text processing: regex URL extraction, domain parsing via urllib.parse, and
content-type classification by domain/path heuristic. No network calls are made —
`entity_mention_count` is left None in v1 because computing it accurately requires
fetching the cited page's content, which is out of scope until page crawling is added
(see PLAN.md section 8 design note).
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse

from provenance.collectors.base import BaseCollector, CitationResult

# Same URL pattern used by probes/base.py's default _extract_urls, so citation extraction
# and probe-level URL capture stay consistent.
_URL_PATTERN = re.compile(r'https?://[^\s\)\]\>"\'<]+')

# Punctuation a sentence commonly ends with, which the regex above over-captures as part
# of the URL (e.g. "...see https://example.com/docs." captures the trailing period).
_TRAILING_PUNCTUATION = ".,;:!?)]}'\">"

_CONTENT_TYPE_HINTS: Dict[str, List[str]] = {
    "docs": ["docs.", "/docs/", "documentation", "reference", "api-reference"],
    "blog": ["blog.", "/blog/", "medium.com", "dev.to", "substack"],
    "comparison": ["vs", "compare", "comparison", "versus", "alternative"],
    "review": ["review", "benchmark", "test", "evaluation"],
    "forum": ["reddit.com", "stackoverflow.com", "news.ycombinator.com", "forum"],
}


class CitationExtractor(BaseCollector):
    collector_name = "citation"

    def collect(self, raw_response: str, entity_name: str) -> List[CitationResult]:
        """
        Extract and classify citation URLs from a raw LLM response string.

        Pure string analysis — no HTTP requests are made. `entity_mention_count` is left
        None (see module docstring). URLs are deduplicated (after trailing punctuation is
        stripped, so "https://x.com." and "https://x.com" collapse to one entry).
        """
        if not raw_response:
            return []

        seen: Set[str] = set()
        results: List[CitationResult] = []

        for raw_match in _URL_PATTERN.findall(raw_response):
            url = raw_match.rstrip(_TRAILING_PUNCTUATION)
            if not url or url in seen:
                continue
            seen.add(url)

            try:
                parsed = urlparse(url)
                domain = parsed.netloc.lower()
                if domain.startswith("www."):
                    domain = domain[len("www."):]
                content_type = self._infer_content_type(url)

                results.append(
                    CitationResult(
                        cited_url=url,
                        domain=domain,
                        content_type=content_type,
                        entity_mention_count=None,
                    )
                )
            except Exception as e:
                results.append(
                    CitationResult(
                        cited_url=url,
                        domain="",
                        error=str(e),
                    )
                )

        return results

    def _infer_content_type(self, url: str) -> Optional[str]:
        url_lower = url.lower()
        for content_type, hints in _CONTENT_TYPE_HINTS.items():
            if any(hint in url_lower for hint in hints):
                return content_type
        return None
