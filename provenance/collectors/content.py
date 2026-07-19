"""
Content/citability collector — fetches the entity's own website and scores how
"citable" the page is for LLM retrieval, writing to the DataPoint EAV store
(CLAUDE.md: "DataPoint — the ever-expanding store").

Failure policy (mirrors SocialCollector): any exception (network, timeout, bad
HTML, non-200) is caught and returned as a single-element list with `error`
set — no signal rows are fabricated. Never raises. A falsy entity_url means
there is nothing to fetch, so collect() returns [] without a network call.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import List, Optional
from urllib.parse import urlparse

import requests

from provenance.collectors.base import BaseCollector
from provenance.config import Settings

_HEADING_TAGS = {"h1", "h2", "h3"}
_TEXT_SKIP_TAGS = {"script", "style", "noscript"}
_LIST_TAGS = {"ul", "ol"}
_STAT_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?%?")
_JSONLD_TYPES = {"faq": "FAQPage", "article": "Article", "organization": "Organization"}


class _ContentHTMLParser(HTMLParser):
    """Single-pass HTML scan collecting everything the collector needs."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text_chunks: List[str] = []
        self.title_chunks: List[str] = []
        self.jsonld_blocks: List[str] = []
        self.heading_count = 0
        self.h1_count = 0
        self.list_count = 0
        self.table_count = 0
        self.link_hrefs: List[str] = []
        self._skip_depth = 0
        self._in_title = False
        self._in_jsonld = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        attrs_dict = dict(attrs)
        if tag in _TEXT_SKIP_TAGS:
            if tag == "script" and (attrs_dict.get("type") or "").lower() == "application/ld+json":
                self._in_jsonld = True
            else:
                self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in _HEADING_TAGS:
            self.heading_count += 1
            if tag == "h1":
                self.h1_count += 1
        elif tag in _LIST_TAGS:
            self.list_count += 1
        elif tag == "table":
            self.table_count += 1
        elif tag == "a" and attrs_dict.get("href"):
            self.link_hrefs.append(attrs_dict["href"])

    def handle_endtag(self, tag: str) -> None:
        if tag in _TEXT_SKIP_TAGS:
            if tag == "script" and self._in_jsonld:
                self._in_jsonld = False
            elif self._skip_depth > 0:
                self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_jsonld:
            self.jsonld_blocks.append(data)
        elif self._in_title:
            self.title_chunks.append(data)
        elif self._skip_depth == 0:
            self.text_chunks.append(data)


@dataclass
class ContentSignalResult:
    signal_key: str
    signal_value: float
    signal_text: Optional[str] = None
    error: Optional[str] = None


class ContentCollector(BaseCollector):
    collector_name = "content"

    def __init__(self, settings: Settings):
        super().__init__(settings)

    def collect(self, entity_url: str) -> List[ContentSignalResult]:
        """
        Fetch entity_url and score how citable the page's content is.

        Produces: word_count, heading_count, has_h1, statistics_density,
        list_count, table_count, external_link_count, has_faq_schema,
        has_article_schema, has_organization_schema, and (only when a
        <title> is present) title_text as a text-only entry (signal_value=0.0).

        Never raises. Any failure (network, timeout, non-200, parse error)
        degrades to a single ContentSignalResult with `error` set. A falsy
        entity_url returns [] — nothing to fetch.
        """
        if not entity_url:
            return []

        try:
            response = requests.get(
                entity_url, timeout=self.settings.content_fetch_timeout_seconds
            )
            response.raise_for_status()

            parser = _ContentHTMLParser()
            parser.feed(response.text)

            text = " ".join(parser.text_chunks)
            words = text.split()
            word_count = len(words)

            stat_tokens = len(_STAT_TOKEN_RE.findall(text))
            statistics_density = round(stat_tokens / word_count * 1000) if word_count else 0

            page_host = urlparse(entity_url).netloc
            external_links = 0
            for href in parser.link_hrefs:
                host = urlparse(href).netloc
                if host and host != page_host:
                    external_links += 1

            schema_types = self._extract_jsonld_types(parser.jsonld_blocks)

            results = [
                ContentSignalResult(signal_key="word_count", signal_value=float(word_count)),
                ContentSignalResult(
                    signal_key="heading_count", signal_value=float(parser.heading_count)
                ),
                ContentSignalResult(
                    signal_key="has_h1", signal_value=1.0 if parser.h1_count >= 1 else 0.0
                ),
                ContentSignalResult(
                    signal_key="statistics_density", signal_value=float(statistics_density)
                ),
                ContentSignalResult(signal_key="list_count", signal_value=float(parser.list_count)),
                ContentSignalResult(
                    signal_key="table_count", signal_value=float(parser.table_count)
                ),
                ContentSignalResult(
                    signal_key="external_link_count", signal_value=float(external_links)
                ),
                ContentSignalResult(
                    signal_key="has_faq_schema",
                    signal_value=1.0 if _JSONLD_TYPES["faq"] in schema_types else 0.0,
                ),
                ContentSignalResult(
                    signal_key="has_article_schema",
                    signal_value=1.0 if _JSONLD_TYPES["article"] in schema_types else 0.0,
                ),
                ContentSignalResult(
                    signal_key="has_organization_schema",
                    signal_value=1.0 if _JSONLD_TYPES["organization"] in schema_types else 0.0,
                ),
            ]

            title_text = "".join(parser.title_chunks).strip()
            if title_text:
                results.append(
                    ContentSignalResult(
                        signal_key="title_text", signal_value=0.0, signal_text=title_text
                    )
                )

            return results

        except Exception as e:
            return [ContentSignalResult(signal_key="content_error", signal_value=0.0, error=str(e))]

    @staticmethod
    def _extract_jsonld_types(blocks: List[str]) -> set:
        """Parse each JSON-LD script block and collect every @type value found,
        including within an @graph array. Blocks that fail to parse are skipped
        (a malformed JSON-LD block must not fail the whole collection)."""
        types: set = set()
        for block in blocks:
            try:
                data = json.loads(block)
            except (json.JSONDecodeError, ValueError):
                continue
            nodes = data if isinstance(data, list) else [data]
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                graph = node.get("@graph")
                candidates = [node, *graph] if isinstance(graph, list) else [node]
                for candidate in candidates:
                    if not isinstance(candidate, dict):
                        continue
                    type_value = candidate.get("@type")
                    if isinstance(type_value, str):
                        types.add(type_value)
                    elif isinstance(type_value, list):
                        types.update(t for t in type_value if isinstance(t, str))
        return types
