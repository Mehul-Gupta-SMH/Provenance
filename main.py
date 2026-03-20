from contextlib import asynccontextmanager
from fastapi import FastAPI

import provenance.models  # noqa: F401 — registers all SQLModel metadata


@asynccontextmanager
async def lifespan(app: FastAPI):
    _register_probes_and_collectors()
    yield


def _register_probes_and_collectors() -> None:
    from provenance.core.registry import ProbeRegistry, CollectorRegistry
    from provenance.probes.anthropic import AnthropicProbe
    from provenance.probes.openai import OpenAIProbe
    from provenance.probes.gemini import GeminiProbe
    from provenance.collectors.demand import DemandCollector
    from provenance.collectors.citation import CitationExtractor

    ProbeRegistry.register("anthropic", AnthropicProbe)
    ProbeRegistry.register("openai", OpenAIProbe)
    ProbeRegistry.register("gemini", GeminiProbe)
    CollectorRegistry.register("demand", DemandCollector)
    CollectorRegistry.register("citation", CitationExtractor)


app = FastAPI(title="Provenance", version="1.0.0", lifespan=lifespan)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "version": "1.0.0"}
