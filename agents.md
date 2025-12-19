# Development Guidelines for Ski Lift Status

This document captures important rules and guidelines for developing the ski lift status scraping pipeline.

## Core Principles

### 0. Config Execution MUST Be HTTP-Only (No Browser Automation)

**CRITICAL**: There are TWO distinct phases in this system:

1. **Discovery Phase** (browser OK for analysis): Finding API endpoints and figuring out extraction patterns
   - Use browser DevTools or Playwright to analyze network traffic
   - Navigate into iframes (e.g., Skiplan embeds status in iframe pointing to live.skiplan.com)
   - Extract configuration parameters (e.g., resort_slug for Skiplan)
   - This is analysis work - done once per resort to create a config

   **Discovery process must:**
   - Accept the status_page_url from status_pages.csv
   - Analyze HTTP requests to find underlying API endpoints
   - For JavaScript-powered pages: find the XHR/fetch calls that load the data
   - For server-rendered pages: use CSS/XPath selectors to extract from HTML
   - Extract platform-specific configuration (resort slugs, map UUIDs, etc.)
   - Output a ResortConfig that can be executed with HTTP-only

   **IMPORTANT**: Every resort CAN be scraped with HTTP-only. There is no such thing as
   "browser required" - you just need to find the right API endpoint or use HTML selectors.
   If JavaScript loads data dynamically, find the API it calls. If data is server-rendered,
   parse the HTML with BeautifulSoup.

2. **Execution Phase** (HTTP ONLY): Running configs to fetch live data
   - **MUST use simple HTTP requests only (httpx)**
   - **NO Playwright, Browserless, or any browser automation**
   - **NO JavaScript rendering**
   - Configs must store direct API endpoint URLs, not status page URLs
   - Must be cheap and fast to run on any platform

### 0.1. Configs MUST Use Provided URLs from status_pages.csv

**CRITICAL**: When generating configs for resorts:

- Configs MUST be generated using the exact `status_page_url` provided in `data/status_pages.csv`
- Do NOT jump to different URLs or find "better" data sources on other domains
- If the provided URL doesn't work with HTTP-only fetching, mark the config as requiring browser automation
- The provided URL is the source of truth - we need to be able to reproduce configs from that URL

**Example:**
- If status_pages.csv says: `https://www.seechamonix.com/lifts/status`
- Config MUST use that URL, NOT `https://en.chamonix.com/informations-remontees-mecaniques-en-temps-reel`

**Why this matters:**
- Browser automation is expensive ($$$) and slow
- Configs should run thousands of times per day at minimal cost
- Any server can make HTTP requests; not all can run browsers
- If a resort requires JavaScript rendering, we need to find their underlying API

**Config structure must include:**
```python
@dataclass
class ResortConfig:
    resort_id: str
    platform: str  # "lumiplan", "skiplan", etc.

    # Direct API endpoints - NOT status page URLs
    api_endpoints: list[str]  # e.g., ["https://api.lumiplan.com/map/{uuid}/dynamicPoiData"]

    # Extraction method
    extraction_type: str  # "json_path", "css_selector", "xpath"
    # ... selectors
```

**Adapters must support:**
```python
def fetch_and_extract(config: ResortConfig) -> ExtractedData:
    """Fetch data using simple HTTP and extract using config."""
    async with httpx.AsyncClient() as client:
        response = await client.get(config.api_endpoints[0])
        return parse_response(response.text, config)
```

### 1. Claude Code's Role: Build, Evaluate, Improve - NOT Execute

**CRITICAL**: Claude Code (the AI assistant) is here to BUILD and IMPROVE the pipeline, NOT to manually execute data extraction.

**Claude Code SHOULD:**
- Write and improve pipeline code that does the scraping, matching, and extraction
- Create automated tests that validate the pipeline
- Analyze pipeline outputs to identify improvements
- Debug pipeline issues and fix the underlying code
- Evaluate results and suggest algorithmic improvements

**Claude Code should NOT:**
- Manually fetch URLs and parse data outside the pipeline
- Manually match lift/run names by writing one-off scripts
- Perform extraction logic that should be in the pipeline
- Do anything that the pipeline should be doing automatically

The goal is a **fully automated pipeline** that can run on any resort without human intervention. If Claude Code finds itself doing manual work, that work should be encoded into the pipeline instead.

### 1. No Resort-Specific Optimizations

**CRITICAL**: When improving the scraping pipeline, NEVER add resort-specific logic or rules.

**Do NOT:**
- Add hardcoded selectors for specific resort websites
- Add resort-specific parsing rules in the LLM prompts
- Create if/else branches based on resort IDs or URLs
- Optimize for specific resort data structures in core logic

**DO:**
- Build general-purpose extraction patterns that work across resorts
- Create reusable platform adapters for common ski resort backends (see below)
- Improve the classification/analysis algorithms to handle more patterns
- Add better heuristics that apply broadly

### 2. Reusable Platform Adapters (NOT Resort-Specific)

Many ski resorts use common backend platforms. When you identify a pattern, create a reusable adapter:

**CRITICAL**: Adapters should ONLY be created for **platforms and technologies**, NOT for specific ski resorts.

**Good adapter examples (platform/technology-based):**
- `lumiplan` - Common European resort platform API
- `skiplan` - Resort management system with getOuvertures.php API
- `nuxtjs` - Nuxt.js __NUXT__ payload extraction pattern
- `nextjs` - Next.js __NEXT_DATA__ payload extraction pattern

**Bad adapter examples (resort-specific - AVOID):**
- `chamonix` - Don't create adapter for a single resort
- `breckenridge` - Don't create adapter for a single resort
- `three_valleys` - Don't create adapter for a single resort

**When to create an adapter:**
1. You identify 2+ resorts using the same platform/technology
2. The platform has a consistent API/data structure
3. The adapter logic would be complex to rediscover each time
4. The adapter is reusable across multiple resorts

**When NOT to create an adapter:**
1. It's only used by a single resort
2. The extraction logic is simple enough to inline
3. It requires resort-specific selectors or URL patterns

**Adapter location:** `src/ski_lift_status/scraping/adapters/`

### 3. Modularity and Readability

- Each pipeline phase should be in its own module
- Functions should do one thing well
- Use clear, descriptive names
- Keep functions under 50 lines where possible
- Add docstrings to all public functions
- Type hints are required for all function signatures

### 3.1. Testing Requirements Before Committing

**CRITICAL**: All tests MUST pass before committing any changes.

```bash
# Run unit tests before committing
PYTHONPATH=src python3 -m pytest tests/ -v

# Run config tests to verify resort adapters work
PYTHONPATH=src python3 scripts/test_configs.py
```

**Requirements:**
- All unit tests in `tests/` must pass
- Config tests should show passing resorts (failures due to external API issues are acceptable)
- New adapters should have corresponding unit tests where practical
- Do NOT commit code that breaks existing tests

### 4. Minimize Data Sent to LLMs

LLM context is expensive and limited. Always:

- **Summarize** large data structures before sending to LLM
- **Filter** irrelevant fields from schemas
- **Truncate** sample content to minimum needed
- **Cache** LLM responses where appropriate
- Use **structured output** schemas to constrain responses
- Prefer **smaller models** (gpt-4o-mini) for simple tasks

Example: Instead of sending full page HTML, send:
- Schema overview with field types
- 3 sample objects
- Matched reference names

### 5. Debugging and Observability

Debugging is critical for understanding pipeline failures.

**Logging Requirements:**
- Use structured logging with `structlog` or similar
- Log at appropriate levels (DEBUG, INFO, WARNING, ERROR)
- Include context: resort_id, phase, resource_url
- Log timing for each phase
- Log coverage metrics at each step

**LangSmith Integration:**
- Enable tracing for all LLM calls
- Tag traces with resort_id and phase
- Include metadata for debugging
- Use runs to group related operations

**Debug Output:**
- Save intermediate results to `debug/` directory
- Include captured resources, classifications, schemas
- Enable with `--debug` flag or `DEBUG=true` env var

### 6. Error Handling

- Never silently swallow exceptions
- Log errors with full context
- Use custom exception classes for pipeline errors
- Implement graceful degradation where possible
- Always return partial results if available

### 7. Testing

- Unit tests for all modules
- Integration tests for pipeline phases
- E2E tests with mock data (no network calls)
- Test edge cases: empty data, malformed JSON, timeouts

### 8. Configuration

- All thresholds should be configurable
- Use environment variables for credentials
- Never commit secrets or API keys
- Document all configuration options

## Environment Setup

Required environment variables in `.env`:

```bash
# OpenAI API (required for config generation)
OPENAI_API_KEY=sk-...

# LangSmith observability (optional but recommended)
LANGCHAIN_API_KEY=ls__...
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=ski-lift-status

# Debug settings
DEBUG=false
LOG_LEVEL=INFO
```

## Common Patterns

### Adding a New Platform Adapter

```python
# src/ski_lift_status/scraping/adapters/lumiplan.py

class LumiplanAdapter:
    """Adapter for Lumiplan/Lumiplay resort platform."""

    # URL patterns that indicate this platform
    URL_PATTERNS = [
        r"lumiplan\.com",
        r"lumiplay\.com",
        r"/api/v\d+/resort/",
    ]

    def detect(self, resources: list[CapturedResource]) -> bool:
        """Check if any resources match this platform."""
        ...

    def extract(self, resources: list[CapturedResource]) -> ExtractedData:
        """Extract lift/run data using platform-specific logic."""
        ...
```

### Adding Debug Logging

```python
import structlog

logger = structlog.get_logger()

def classify_resource(resource: CapturedResource) -> ClassifiedResource:
    logger.debug(
        "classifying_resource",
        url=resource.url,
        content_type=resource.content_type,
        size_bytes=resource.size_bytes,
    )

    result = _do_classification(resource)

    logger.info(
        "resource_classified",
        url=resource.url,
        category=result.category,
        lift_coverage=result.lift_coverage,
        confidence=result.confidence_score,
    )

    return result
```

## Decision Log

Document significant architectural decisions here:

| Date | Decision | Rationale |
|------|----------|-----------|
| 2024-12-18 | 6-phase pipeline | Matches issue requirements, allows debugging at each step |
| 2024-12-18 | 20% coverage threshold | Per issue requirements, balances precision vs recall |
| 2024-12-18 | LangGraph for agent | Provides state management and retry logic |
