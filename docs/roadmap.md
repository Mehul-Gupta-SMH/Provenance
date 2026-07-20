# Provenance — Roadmap & GEO Research Notes

Synthesis of a competitive scan of open-source GEO / AI-visibility tooling and
the academic GEO literature, mapped onto Provenance's architecture (registry
collectors, flat schema, read-time derivation, the `DataPoint` EAV store). This
is the source of truth for post-v1 feature prioritization.

## Prior art surveyed

| Project | What we borrowed |
|---|---|
| [Auriti-Labs/geo-optimizer-skill](https://github.com/Auriti-Labs/geo-optimizer-skill) | Weighted 0–100 discoverability rubric (robots.txt AI-bot tiers, llms.txt, JSON-LD, `.well-known`), citability factor taxonomy, CI regression gate, MCP server |
| [AI2HU/gego](https://github.com/AI2HU/gego) | Canonical brand **aliases** (shipped ✓), citation-domain analytics (shipped ✓), cron scheduling, AI-assisted prompt generation, provider distribution |
| [sarahkb125/llm-brand-tracker](https://github.com/sarahkb125/llm-brand-tracker) | Website-scraping baseline positioning, "where you should be mentioned but aren't" gap logic (note: naive LLM prompt-gen produces near-duplicate prompts — optimize for *diversity*) |
| [ai-search-guru/getcito](https://github.com/ai-search-guru/getcito...) | Transparency-as-differentiator; multi-surface scraper registry (AI Overviews/Copilot that have no API) |
| GEO paper (Aggarwal et al., KDD'24, [arXiv:2311.09735](https://arxiv.org/abs/2311.09735)); [AutoGEO](https://github.com/cxcscmu/AutoGEO) (ICLR'26) | Position-adjusted word count, subjective-impression metric, and **which content interventions actually work** |

## Key reference rubrics (embedded so they survive)

### Discoverability score — 8 weighted categories (0–100), from geo-optimizer-skill
`robots` 18 · `llms` 18 · `schema` 16 · `meta` 14 · `content` 12 · `brand_entity` 10 · `signals` 6 · `ai_discovery` 6, then a severity-tiered negative penalty (high −15 / med −10 / low −5).
Bands: **excellent 86–100 · good 68–85 · foundation 36–67 · critical 0–35**.
robots.txt weighting hinges on the four **citation bots** specifically (`OAI-SearchBot`, `ClaudeBot`, `Claude-SearchBot`, `PerplexityBot`) being allowed, not just "any AI bot" — 13 of the 18 robots points.

### Position-Adjusted Word Count (PAWC), from the GEO paper
`wc_adj(cᵢ, r) = Σ_{s ∈ S_cᵢ} |s| · (1 − pos(s)/|S|)` — sum the word counts of sentences mentioning the entity, each **down-weighted linearly by its position** in the response (earlier = heavier). A strict generalization of "how much of the answer is about entity X," rewarding *early* prominence.

### Which content signals move LLM visibility (GEO paper headline result)
**Quotation density ≈ Statistics density ≈ Cited-source density** (~30–41% PAWC lift) **>** fluency **>** readability/technical-terms/authoritative-tone **>** **keyword stuffing (≈ −8.7%, actively harmful).** → prioritize quotation/statistic/citation detectors in the content collector; ignore keyword-density heuristics.

## Prioritized backlog

Shipped post-v1: raw signal inspection · context sweep · experiment analytics (comparison/drift) · social collector (DataPoint) · action report · citation-domain analytics · content/citability collector · entity aliases · **discoverability collector** · **composite 0–100 GEO score** · **content density signals (quotation/citation)**.

| Rank | Feature | Seam | Effort | Migration |
|---|---|---|---|---|
| ~~1~~ ✅ | **Discoverability collector** (robots.txt bot tiers, llms.txt, JSON-LD, `.well-known`) | `collectors/discoverability.py` → `DataPoint(signal_family="discoverability")` | S | No |
| ~~2~~ ✅ | **Composite 0–100 GEO score** (named weighted sub-components, bands) | read-time `core/geo_score.py`, `GET /v1/runs/{id}/geo-score` | M | No |
| ~~3~~ ✅ | **Content density signals** (quotation / statistic / external-citation density) | extend `collectors/content.py` | S | No |
| 4 | **LLM-generated query variants** (diversity-optimized, hybrid with the 4 fixed templates) | `core/query_generation.py` + pipeline flag | M | No |
| 5 | **Position-adjusted visibility metric** folded into divergence/fingerprint | `core/divergence.py` + `DataPoint(signal_family="visibility")` | M | No |
| 6 | **CI regression-gate** endpoint (`min_score`, sarif/junit output) | `core/gating.py`, `POST /v1/runs/{id}/gate` | S | No |
| 7 | **Scheduled recurring runs** feeding experiment drift (APScheduler, in-process — no Celery in v1) | `models/schedule.py` + `core/scheduler.py` | M | Yes |
| 8 | **MCP server** exposing Provenance to Claude/Cursor | `mcp/server.py` wrapping service functions | M | No |
| 9 | **Provider-distribution / cross-model** analytics (needs real OpenAI/Gemini probes) | read-time endpoint + un-stub probes | M–L | No |

Guardrail (from C-SEO Bench, NeurIPS D&B'25): treat any single paper's optimization list as a hypothesis, not gospel — content-quality signals still dominate, and effects are *relative to current visibility*, not flat additive boosts.
