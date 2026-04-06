"""
Run orchestration pipeline.

Flow:
  1. Load run + entity from DB
  2. Generate query matrix (seeds × variants × perturbations)
  3. For each registered provider × each query: probe → write QueryProbe + LLMSignal + Citation
  4. Mark run completed (or failed)

Called from FastAPI background tasks. Creates its own DB session (the route's session
is closed before the background task executes).
"""
import json
import logging
from datetime import datetime
from urllib.parse import urlparse

from sqlmodel import Session

from provenance.config import get_settings
from provenance.core.query_generator import QueryGenerator
from provenance.core.registry import ProbeRegistry
from provenance.models.citation import Citation
from provenance.models.database import engine
from provenance.models.entity import Entity
from provenance.models.llm_signal import LLMSignal
from provenance.models.query_probe import QueryProbe
from provenance.models.run import Run, RunStatus
from provenance.probes.base import ProbeContext

logger = logging.getLogger(__name__)


async def execute_run(run_id: int) -> None:
    """
    Main pipeline entrypoint. Called as a FastAPI background task.

    Creates its own DB session. All writes are committed per-provider so partial
    results are preserved if a later provider fails.
    """
    settings = get_settings()

    with Session(engine) as session:
        run = session.get(Run, run_id)
        if run is None:
            logger.error("execute_run: run %d not found", run_id)
            return

        run.status = RunStatus.running
        run.started_at = datetime.utcnow()
        session.add(run)
        session.commit()

        try:
            await _run_pipeline(run, session, settings)
        except Exception as exc:
            logger.exception("Run %d failed: %s", run_id, exc)
            session.refresh(run)
            run.status = RunStatus.failed
            run.error_message = str(exc)
            run.completed_at = datetime.utcnow()
            session.add(run)
            session.commit()


async def _run_pipeline(run: Run, session: Session, settings) -> None:
    entity = session.get(Entity, run.entity_id)
    if entity is None:
        raise ValueError(f"Entity {run.entity_id} not found")

    query_seeds = json.loads(entity.query_seeds_json or "[]")
    competitors = json.loads(entity.competitors_json or "[]")

    if not query_seeds:
        raise ValueError(
            f"Entity '{entity.name}' has no query_seeds — cannot run probes"
        )

    generator = QueryGenerator(perturbations_per_variant=3)
    queries = generator.generate(
        query_seeds=query_seeds,
        entity_name=entity.name,
        competitors=competitors,
    )
    logger.info(
        "Run %d: entity=%s, %d queries across %d provider(s)",
        run.id, entity.name, len(queries), len(ProbeRegistry.list()),
    )

    for provider_name in ProbeRegistry.list():
        ProbeClass = ProbeRegistry.get(provider_name)
        probe_instance = ProbeClass(settings)

        for gq in queries:
            context = ProbeContext(temperature=settings.anthropic_default_temperature)

            result = await probe_instance.probe(
                query=gq.text,
                query_variant=gq.variant,
                entity_name=entity.name,
                context=context,
                competitors=competitors,
            )

            qp = QueryProbe(
                run_id=run.id,
                query_variant=result.query_variant,
                perturbation_index=gq.perturbation_index,
                query_text=result.query_text,
                raw_response=result.raw_response,
                probed_at=result.probed_at,
                provider=result.provider,
                model=result.model,
                temperature=context.temperature,
            )
            session.add(qp)
            session.flush()  # populate qp.id before writing children

            for ex in result.extracted_entities:
                session.add(
                    LLMSignal(
                        entry_id=qp.id,
                        recommendation_rank=ex.recommendation_rank,
                        mention_type=ex.mention_type,
                        phrasing_sentiment=ex.phrasing_sentiment,
                        context_of_mention=ex.context_of_mention,
                        co_mentioned_entities_json=json.dumps(ex.co_mentioned_entities),
                    )
                )

            for url in result.cited_urls:
                domain = urlparse(url).netloc or url
                session.add(Citation(entry_id=qp.id, cited_url=url, domain=domain))

            if result.error:
                logger.warning(
                    "Run %d / %s / %s[%d]: %s",
                    run.id, provider_name, gq.variant, gq.perturbation_index, result.error,
                )

        session.commit()
        logger.info("Run %d: provider=%s complete", run.id, provider_name)

    run.status = RunStatus.completed
    run.completed_at = datetime.utcnow()
    session.add(run)
    session.commit()
    logger.info("Run %d completed", run.id)
