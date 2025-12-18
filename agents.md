# Development Guidelines for Ski Lift Status

This document captures important rules and guidelines for developing the ski lift status scraping pipeline.

## Core Principles

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

### 2. Reusable Platform Adapters

Many ski resorts use common backend platforms. When you identify a pattern, create a reusable adapter:

**Known Platforms:**
- `lumiplan` / `lumiplay` - Common European resort platform
- `skiplan` - Resort management system
- `infosnow` - Swiss resort data platform
- `intrawest` - North American resort management
- `powdr` - Resort management company platform
- `dolomiti_superski` - Dolomites region platform
- `skidata` - Ticketing/access platform with status data

**When to create an adapter:**
1. You identify 2+ resorts using the same platform
2. The platform has a consistent API/data structure
3. The adapter logic would be complex to rediscover each time

**Adapter location:** `src/ski_lift_status/scraping/adapters/`

### 3. Modularity and Readability

- Each pipeline phase should be in its own module
- Functions should do one thing well
- Use clear, descriptive names
- Keep functions under 50 lines where possible
- Add docstrings to all public functions
- Type hints are required for all function signatures

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
