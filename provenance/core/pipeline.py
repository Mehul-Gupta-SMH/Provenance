"""
RunPipeline — orchestrates a full Provenance run for one entity (PLAN.md section 9).

Called by the FastAPI background-task adapter in api/v1/routes/runs.py. Pure async
orchestration — no FastAPI dependency injection here; the caller supplies its own
Session (see Risk 3 in PLAN.md: the pipeline commits incrementally so a crash
mid-run leaves consistent partial data, rather than one giant transaction).

Write semantics (PLAN.md v1.1 reconciliation, delta #2): LLMSignal carries no
entity_id — one row per QueryProbe, describing the run's own entity only.
Competitor mentions are folded into co_mentioned_entities_json, never written as
separate signal rows. DemandSignal likewise carries no entity_id (only run_id);
v1 collects demand once per run, for the run's own entity.

Failure semantics: a probe soft-failure (ProbeResult.error set) still produces a
QueryProbe row (with the error captured in raw_response) and an "absent" LLMSignal
row — it does not fail the run. The run only fails when the entity is missing,
every probe for the run errored, or an unexpected exception escapes the pipeline.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlmodel import Session

from provenance.collectors.citation import CitationExtractor
from provenance.config import Settings
from provenance.core.divergence import DivergenceEngine
from provenance.core.registry import CollectorRegistry, ProbeRegistry
from provenance.models.citation import Citation
from provenance.models.data_point import DataPoint
from provenance.models.demand_signal import DemandSignal
from provenance.models.entity import Entity, matches_entity
from provenance.models.llm_signal import LLMSignal
from provenance.models.query_probe import QueryProbe
from provenance.models.run import ProbeContextSpec, Run, RunStatus
from provenance.probes.base import ExtractedEntity, ProbeContext

logger = logging.getLogger(__name__)

# The four query variants for v1 probes (PLAN.md section 7 / open decisions table).
# Only `category` is interpolated — the query intentionally does not name the run's
# own entity, so the probe reflects an unprompted recommendation.
_QUERY_TEMPLATES: Dict[str, str] = {
    "direct": "What is the best {category}?",
    "comparative": "Compare the top options for {category}. Which would you recommend?",
    "expert": "As a technical expert, which {category} would you choose for a production "
    "environment?",
    "contrarian": "What is the most underrated option for {category} that experts often miss?",
}

# v1 scope boundary (PLAN.md): only the Anthropic probe is functional; OpenAI/Gemini
# are stubs. Looked up by name via ProbeRegistry — the class is never hardcoded.
_PROVIDERS: Tuple[str, ...] = ("anthropic",)


class RunPipeline:
    """Orchestrates a full Provenance run for one entity."""

    def __init__(self, settings: Settings, session: Session) -> None:
        self.settings = settings
        self.session = session

    async def execute(self, run_id: int) -> None:
        run = self.session.get(Run, run_id)
        if run is None:
            logger.error("Run %s not found", run_id)
            return

        entity = self.session.get(Entity, run.entity_id)
        if entity is None:
            self._fail_run(run, f"Entity {run.entity_id} not found")
            return

        run.status = RunStatus.running
        run.started_at = datetime.utcnow()
        self.session.add(run)
        self.session.commit()

        try:
            competitors: List[str] = json.loads(entity.competitors_json)

            await self._collect_demand_signal(entity, run)

            try:
                await self._collect_social_signals(entity, run)
            except Exception:
                # Social signals are best-effort DataPoint rows — a failure here
                # must never fail an otherwise-healthy run.
                logger.exception("Social signal collection failed for run %s", run_id)

            try:
                await self._collect_content_signals(entity, run)
            except Exception:
                # Content signals are best-effort DataPoint rows — a failure here
                # must never fail an otherwise-healthy run.
                logger.exception("Content signal collection failed for run %s", run_id)

            total_probes = 0
            failed_probes = 0
            for provider_name in _PROVIDERS:
                total, failed = await self._execute_provider_probes(
                    run, entity, competitors, provider_name
                )
                total_probes += total
                failed_probes += failed

            if total_probes > 0 and failed_probes == total_probes:
                self._fail_run(run, f"All {total_probes} probe(s) failed for run {run.id}")
                return

            run.status = RunStatus.completed
            run.completed_at = datetime.utcnow()
            self.session.add(run)
            self.session.commit()

            try:
                DivergenceEngine(self.session).compute_for_run(run.id)
            except Exception:
                # Divergence is a read-time derived cache — a failure here must
                # never mark an otherwise-completed run as failed.
                logger.exception("Divergence computation failed for run %s", run_id)

        except Exception as e:  # unrecoverable — only path besides entity-missing/all-failed
            logger.exception("Pipeline failed for run %s", run_id)
            self._fail_run(run, str(e))

    # ------------------------------------------------------------------
    # Demand signal (once per run, own entity only)
    # ------------------------------------------------------------------

    async def _collect_demand_signal(self, entity: Entity, run: Run) -> None:
        collector_cls = CollectorRegistry.get("demand")
        collector = collector_cls(self.settings)
        # DemandCollector is sync and sleeps between pytrends calls — run off the event loop.
        result = await asyncio.to_thread(collector.collect, entity.name, entity.category)

        signal = DemandSignal(
            run_id=run.id,
            search_volume=result.search_volume,
            trend_velocity=result.trend_velocity,
            related_queries_json=json.dumps(result.related_queries),
            geographic_distribution_json=json.dumps(result.geographic_distribution),
        )
        self.session.add(signal)
        self.session.commit()

    # ------------------------------------------------------------------
    # Social signal (once per run, own entity only) — writes to DataPoint
    # ------------------------------------------------------------------

    async def _collect_social_signals(self, entity: Entity, run: Run) -> None:
        collector_cls = CollectorRegistry.get("social")
        collector = collector_cls(self.settings)
        # SocialCollector is sync (requests) — run off the event loop.
        results = await asyncio.to_thread(collector.collect, entity.name)

        for result in results:
            if result.error:
                logger.warning(
                    "Social signal collection error for run %s: %s", run.id, result.error
                )
                continue
            self.session.add(
                DataPoint(
                    run_id=run.id,
                    signal_family="social",
                    signal_key=result.signal_key,
                    signal_value=result.signal_value,
                    signal_text=result.signal_text,
                    collector_name="social",
                )
            )
        self.session.commit()

    # ------------------------------------------------------------------
    # Content signal (once per run, own entity only) — writes to DataPoint
    # ------------------------------------------------------------------

    async def _collect_content_signals(self, entity: Entity, run: Run) -> None:
        if not entity.url:
            return

        collector_cls = CollectorRegistry.get("content")
        collector = collector_cls(self.settings)
        # ContentCollector is sync (requests) — run off the event loop.
        results = await asyncio.to_thread(collector.collect, entity.url)

        for result in results:
            if result.error:
                logger.warning(
                    "Content signal collection error for run %s: %s", run.id, result.error
                )
                continue
            self.session.add(
                DataPoint(
                    run_id=run.id,
                    signal_family="content",
                    signal_key=result.signal_key,
                    signal_value=result.signal_value,
                    signal_text=result.signal_text,
                    collector_name="content",
                )
            )
        self.session.commit()

    # ------------------------------------------------------------------
    # LLM probes (per variant, per provider)
    # ------------------------------------------------------------------

    async def _execute_provider_probes(
        self,
        run: Run,
        entity: Entity,
        competitors: List[str],
        provider_name: str,
    ) -> Tuple[int, int]:
        """Run every query variant for one provider. Returns (total, failed) probe counts."""
        probe_cls = ProbeRegistry.get(provider_name)
        probe = probe_cls(self.settings)
        citation_extractor = CitationExtractor(self.settings)
        contexts = self._build_probe_contexts(run)

        total = 0
        failed = 0
        for context in contexts:
            for variant, template in _QUERY_TEMPLATES.items():
                query = template.format(category=entity.category)

                result = await probe.probe(
                    query=query,
                    query_variant=variant,
                    entity_name=entity.name,
                    context=context,
                    competitors=competitors,
                )
                total += 1
                if result.error:
                    failed += 1

                raw_response = result.raw_response
                if result.error:
                    # QueryProbe has no dedicated error column — the soft-failure is
                    # captured in raw_response itself so the row still records it.
                    raw_response = f"[PROBE ERROR] {result.error}"

                qp = QueryProbe(
                    run_id=run.id,
                    query_variant=variant,
                    query_text=query,
                    raw_response=raw_response,
                    probed_at=result.probed_at,
                    country=context.country,
                    region=context.region,
                    language=context.language,
                    locale=context.locale,
                    user_persona=context.user_persona,
                    expertise_level=context.expertise_level,
                    stated_use_case=context.stated_use_case,
                    provider=result.provider,
                    model=result.model,
                    temperature=context.temperature,
                    system_prompt_variant=context.system_prompt_variant,
                    prior_context=context.prior_context,
                )
                self.session.add(qp)
                self.session.flush()  # populate qp.id for the FKs below, without committing yet

                # One LLMSignal row per probe, describing the run's own entity only.
                # Competitors are folded into co_mentioned_entities_json (delta #2).
                own_entity = self._find_own_entity(result.extracted_entities, entity)
                co_mentioned = [
                    e.name
                    for e in result.extracted_entities
                    if not matches_entity(e.name, entity)
                ]
                signal = LLMSignal(
                    entry_id=qp.id,
                    recommendation_rank=own_entity.recommendation_rank if own_entity else None,
                    mention_type=own_entity.mention_type if own_entity else "absent",
                    phrasing_sentiment=own_entity.phrasing_sentiment if own_entity else None,
                    context_of_mention=own_entity.context_of_mention if own_entity else None,
                    co_mentioned_entities_json=json.dumps(co_mentioned),
                )
                self.session.add(signal)

                for c in citation_extractor.collect(result.raw_response, entity.name):
                    citation = Citation(
                        entry_id=qp.id,
                        cited_url=c.cited_url,
                        domain=c.domain,
                        content_type=c.content_type,
                        entity_mention_count=c.entity_mention_count,
                    )
                    self.session.add(citation)

                self.session.commit()

        return total, failed

    def _build_probe_contexts(self, run: Run) -> List[ProbeContext]:
        """One ProbeContext per entry in run.probe_contexts_json (the fan-out matrix).

        An empty list (today's default RunCreate) yields a single default context —
        byte-for-byte identical to v1's pre-context-sweep behavior.
        """
        specs = json.loads(run.probe_contexts_json)
        if not specs:
            specs = [{}]
        return [self._build_probe_context(ProbeContextSpec(**spec)) for spec in specs]

    def _build_probe_context(self, spec: ProbeContextSpec) -> ProbeContext:
        """Build a ProbeContext from a spec, falling back to ProbeContext's own
        defaults for unset fields (temperature falls back to the configured
        Anthropic default, as v1 did before context sweep existed)."""
        kwargs: Dict[str, object] = {"temperature": self.settings.anthropic_default_temperature}
        for field_name in (
            "country", "region", "language", "locale", "user_persona",
            "expertise_level", "stated_use_case", "temperature", "system_prompt_variant",
        ):
            value = getattr(spec, field_name)
            if value is not None:
                kwargs[field_name] = value
        return ProbeContext(**kwargs)

    def _find_own_entity(
        self, extracted_entities: List[ExtractedEntity], entity: Entity
    ) -> Optional[ExtractedEntity]:
        """
        Locate the run's own entity among the extraction results (alias-aware,
        case-insensitive name match). None means the LLM did not mention the
        entity under any known name, in which case the LLMSignal row records
        mention_type="absent".
        """
        for e in extracted_entities:
            if matches_entity(e.name, entity):
                return e
        return None

    def _fail_run(self, run: Run, error: str) -> None:
        run.status = RunStatus.failed
        run.completed_at = datetime.utcnow()
        run.error_message = error
        self.session.add(run)
        self.session.commit()
