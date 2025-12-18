"""
Status normalizer for ski lift and trail statuses.

Provides a consistent enumerated schema for lift statuses and uses LLM with
structured outputs to classify incoming statuses from various sources and languages.

Normalized Status Schema:
- OPEN: Lift/trail is currently operating and open to the public
- CLOSED: Lift/trail is closed and not operating
- EXPECTED_TO_OPEN: Lift/trail is expected to open (e.g., forecast, scheduled)
- NOT_EXPECTED_TO_OPEN: Lift/trail is not expected to open (e.g., out of season, maintenance)
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel


class NormalizedStatus(str, Enum):
    """Normalized status for lifts and trails.

    This enum provides a consistent schema for status values across
    different resort platforms and languages.
    """
    OPEN = "open"
    CLOSED = "closed"
    EXPECTED_TO_OPEN = "expected_to_open"
    NOT_EXPECTED_TO_OPEN = "not_expected_to_open"


# Static mappings for known status strings
# These are resolved without LLM calls for efficiency
KNOWN_STATUS_MAPPINGS: dict[str, NormalizedStatus] = {
    # English - Open
    "open": NormalizedStatus.OPEN,
    "opened": NormalizedStatus.OPEN,
    "operating": NormalizedStatus.OPEN,
    "running": NormalizedStatus.OPEN,
    "available": NormalizedStatus.OPEN,
    "in service": NormalizedStatus.OPEN,

    # English - Closed
    "closed": NormalizedStatus.CLOSED,
    "close": NormalizedStatus.CLOSED,
    "not operating": NormalizedStatus.CLOSED,
    "unavailable": NormalizedStatus.CLOSED,
    "out of service": NormalizedStatus.CLOSED,
    "stopped": NormalizedStatus.CLOSED,
    "suspended": NormalizedStatus.CLOSED,
    "on hold": NormalizedStatus.CLOSED,
    "maintenance": NormalizedStatus.CLOSED,
    "wind hold": NormalizedStatus.CLOSED,

    # English - Expected to open
    "forecast": NormalizedStatus.EXPECTED_TO_OPEN,
    "scheduled": NormalizedStatus.EXPECTED_TO_OPEN,
    "expected": NormalizedStatus.EXPECTED_TO_OPEN,
    "planned": NormalizedStatus.EXPECTED_TO_OPEN,
    "opening soon": NormalizedStatus.EXPECTED_TO_OPEN,
    "will open": NormalizedStatus.EXPECTED_TO_OPEN,
    "waiting": NormalizedStatus.EXPECTED_TO_OPEN,

    # English - Not expected to open
    "out_of_period": NormalizedStatus.NOT_EXPECTED_TO_OPEN,
    "out of period": NormalizedStatus.NOT_EXPECTED_TO_OPEN,
    "out of season": NormalizedStatus.NOT_EXPECTED_TO_OPEN,
    "seasonal closure": NormalizedStatus.NOT_EXPECTED_TO_OPEN,
    "not available": NormalizedStatus.NOT_EXPECTED_TO_OPEN,
    "permanently closed": NormalizedStatus.NOT_EXPECTED_TO_OPEN,
    "decommissioned": NormalizedStatus.NOT_EXPECTED_TO_OPEN,

    # French - Open
    "ouvert": NormalizedStatus.OPEN,
    "ouverte": NormalizedStatus.OPEN,
    "en service": NormalizedStatus.OPEN,
    "en fonctionnement": NormalizedStatus.OPEN,

    # French - Closed
    "fermé": NormalizedStatus.CLOSED,
    "ferme": NormalizedStatus.CLOSED,
    "fermée": NormalizedStatus.CLOSED,
    "fermee": NormalizedStatus.CLOSED,
    "hors service": NormalizedStatus.CLOSED,
    "suspendu": NormalizedStatus.CLOSED,
    "arrêté": NormalizedStatus.CLOSED,
    "arrete": NormalizedStatus.CLOSED,
    "arrêt vent": NormalizedStatus.CLOSED,
    "arret vent": NormalizedStatus.CLOSED,
    "en attente": NormalizedStatus.EXPECTED_TO_OPEN,

    # French - Expected
    "prévu": NormalizedStatus.EXPECTED_TO_OPEN,
    "prevu": NormalizedStatus.EXPECTED_TO_OPEN,
    "prévision": NormalizedStatus.EXPECTED_TO_OPEN,
    "prevision": NormalizedStatus.EXPECTED_TO_OPEN,

    # French - Not expected
    "hors période": NormalizedStatus.NOT_EXPECTED_TO_OPEN,
    "hors periode": NormalizedStatus.NOT_EXPECTED_TO_OPEN,
    "hors saison": NormalizedStatus.NOT_EXPECTED_TO_OPEN,

    # German - Open
    "offen": NormalizedStatus.OPEN,
    "geöffnet": NormalizedStatus.OPEN,
    "geoffnet": NormalizedStatus.OPEN,
    "in betrieb": NormalizedStatus.OPEN,

    # German - Closed
    "geschlossen": NormalizedStatus.CLOSED,
    "gesperrt": NormalizedStatus.CLOSED,
    "außer betrieb": NormalizedStatus.CLOSED,
    "ausser betrieb": NormalizedStatus.CLOSED,
    "wind pause": NormalizedStatus.CLOSED,

    # German - Expected
    "geplant": NormalizedStatus.EXPECTED_TO_OPEN,
    "erwartet": NormalizedStatus.EXPECTED_TO_OPEN,

    # German - Not expected
    "saisonschluss": NormalizedStatus.NOT_EXPECTED_TO_OPEN,
    "außerhalb der saison": NormalizedStatus.NOT_EXPECTED_TO_OPEN,
    "ausserhalb der saison": NormalizedStatus.NOT_EXPECTED_TO_OPEN,

    # Italian - Open
    "aperto": NormalizedStatus.OPEN,
    "aperta": NormalizedStatus.OPEN,
    "in funzione": NormalizedStatus.OPEN,

    # Italian - Closed
    "chiuso": NormalizedStatus.CLOSED,
    "chiusa": NormalizedStatus.CLOSED,
    "fuori servizio": NormalizedStatus.CLOSED,
    "sospeso": NormalizedStatus.CLOSED,

    # Italian - Expected
    "previsto": NormalizedStatus.EXPECTED_TO_OPEN,
    "programmato": NormalizedStatus.EXPECTED_TO_OPEN,

    # Italian - Not expected
    "fuori stagione": NormalizedStatus.NOT_EXPECTED_TO_OPEN,

    # Spanish - Open
    "abierto": NormalizedStatus.OPEN,
    "abierta": NormalizedStatus.OPEN,
    "operativo": NormalizedStatus.OPEN,

    # Spanish - Closed
    "cerrado": NormalizedStatus.CLOSED,
    "cerrada": NormalizedStatus.CLOSED,
    "suspendido": NormalizedStatus.CLOSED,

    # Spanish - Expected
    "previsto": NormalizedStatus.EXPECTED_TO_OPEN,
    "programado": NormalizedStatus.EXPECTED_TO_OPEN,

    # Spanish - Not expected
    "fuera de temporada": NormalizedStatus.NOT_EXPECTED_TO_OPEN,
}


class StatusNormalizationResult(BaseModel):
    """Result of normalizing a status string."""
    original_status: str
    normalized_status: NormalizedStatus
    confidence: float  # 1.0 for static mapping, varies for LLM
    source: str  # "static_mapping" or "llm"


class LLMStatusResponse(BaseModel):
    """Structured response from LLM for status classification."""
    normalized_status: NormalizedStatus
    reasoning: str


# Cache for LLM-normalized statuses to avoid repeated API calls
_llm_status_cache: dict[str, NormalizedStatus] = {}


def normalize_status_static(raw_status: str) -> NormalizedStatus | None:
    """Attempt to normalize a status using static mappings.

    Args:
        raw_status: The raw status string from the source

    Returns:
        NormalizedStatus if found in static mappings, None otherwise
    """
    if not raw_status:
        return None

    # Normalize the input
    normalized = raw_status.lower().strip()
    normalized = normalized.replace("_", " ").replace("-", " ")

    # Direct lookup
    if normalized in KNOWN_STATUS_MAPPINGS:
        return KNOWN_STATUS_MAPPINGS[normalized]

    # Try without spaces (for cases like "OUT_OF_PERIOD" -> "outofperiod")
    no_spaces = normalized.replace(" ", "")
    for key, value in KNOWN_STATUS_MAPPINGS.items():
        if key.replace(" ", "") == no_spaces:
            return value

    return None


async def normalize_status_llm(
    raw_status: str,
    context: str | None = None,
) -> NormalizedStatus:
    """Normalize a status using LLM with structured outputs.

    Uses OpenAI's structured outputs to ensure a valid NormalizedStatus is returned.
    Results are cached to avoid repeated API calls for the same status string.

    Args:
        raw_status: The raw status string to normalize
        context: Optional context about the status (e.g., resort name, language)

    Returns:
        NormalizedStatus enum value
    """
    # Check cache first
    cache_key = raw_status.lower().strip()
    if cache_key in _llm_status_cache:
        return _llm_status_cache[cache_key]

    from openai import AsyncOpenAI

    client = AsyncOpenAI()

    system_prompt = """You are a ski resort status classifier. Your task is to classify lift/trail status strings into one of four normalized categories:

1. OPEN: The lift/trail is currently operating and open to the public
2. CLOSED: The lift/trail is closed and not operating (temporary closures, wind holds, maintenance)
3. EXPECTED_TO_OPEN: The lift/trail is expected to open (scheduled, forecast, waiting to open)
4. NOT_EXPECTED_TO_OPEN: The lift/trail is not expected to open (out of season, permanently closed)

Status strings may be in any language (English, French, German, Italian, Spanish, etc.).
Always respond with a valid status classification."""

    user_prompt = f"Classify this ski lift/trail status: \"{raw_status}\""
    if context:
        user_prompt += f"\nContext: {context}"

    response = await client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format=LLMStatusResponse,
        temperature=0.0,
    )

    result = response.choices[0].message.parsed
    if result is None:
        # Fallback to CLOSED if parsing fails
        return NormalizedStatus.CLOSED

    # Cache the result
    _llm_status_cache[cache_key] = result.normalized_status

    return result.normalized_status


async def normalize_status(
    raw_status: str,
    use_llm: bool = True,
    context: str | None = None,
) -> StatusNormalizationResult:
    """Normalize a status string to the standard schema.

    First attempts static mapping, falls back to LLM if enabled.

    Args:
        raw_status: The raw status string from the source
        use_llm: Whether to use LLM for unknown statuses (default True)
        context: Optional context for LLM classification

    Returns:
        StatusNormalizationResult with the normalized status and metadata
    """
    if not raw_status:
        return StatusNormalizationResult(
            original_status="",
            normalized_status=NormalizedStatus.CLOSED,
            confidence=0.0,
            source="default",
        )

    # Try static mapping first
    static_result = normalize_status_static(raw_status)
    if static_result is not None:
        return StatusNormalizationResult(
            original_status=raw_status,
            normalized_status=static_result,
            confidence=1.0,
            source="static_mapping",
        )

    # Fall back to LLM if enabled
    if use_llm:
        llm_result = await normalize_status_llm(raw_status, context)
        return StatusNormalizationResult(
            original_status=raw_status,
            normalized_status=llm_result,
            confidence=0.9,  # High confidence for LLM structured output
            source="llm",
        )

    # Default to CLOSED for unknown statuses when LLM is disabled
    return StatusNormalizationResult(
        original_status=raw_status,
        normalized_status=NormalizedStatus.CLOSED,
        confidence=0.5,
        source="default",
    )


def normalize_status_sync(raw_status: str) -> NormalizedStatus:
    """Synchronous version using only static mappings.

    Use this when you don't need LLM fallback or in sync contexts.

    Args:
        raw_status: The raw status string from the source

    Returns:
        NormalizedStatus enum value
    """
    result = normalize_status_static(raw_status)
    if result is not None:
        return result

    # Default fallback
    return NormalizedStatus.CLOSED


async def normalize_statuses_batch(
    raw_statuses: list[str],
    use_llm: bool = True,
) -> dict[str, NormalizedStatus]:
    """Normalize a batch of status strings efficiently.

    Groups statuses by whether they need LLM processing and batches LLM calls.

    Args:
        raw_statuses: List of raw status strings
        use_llm: Whether to use LLM for unknown statuses

    Returns:
        Dict mapping original status strings to normalized statuses
    """
    results: dict[str, NormalizedStatus] = {}
    unknown_statuses: list[str] = []

    # First pass: handle known statuses
    for status in raw_statuses:
        if not status:
            results[status] = NormalizedStatus.CLOSED
            continue

        static_result = normalize_status_static(status)
        if static_result is not None:
            results[status] = static_result
        else:
            unknown_statuses.append(status)

    # Second pass: handle unknown statuses with LLM
    if unknown_statuses and use_llm:
        for status in unknown_statuses:
            llm_result = await normalize_status_llm(status)
            results[status] = llm_result
    elif unknown_statuses:
        for status in unknown_statuses:
            results[status] = NormalizedStatus.CLOSED

    return results


def get_known_mappings() -> dict[str, NormalizedStatus]:
    """Get a copy of all known static status mappings.

    Useful for debugging and documentation.
    """
    return KNOWN_STATUS_MAPPINGS.copy()


def add_custom_mapping(status: str, normalized: NormalizedStatus) -> None:
    """Add a custom status mapping at runtime.

    This is useful for adding resort-specific status strings that
    were discovered via LLM but should be handled statically in the future.

    Args:
        status: The raw status string (will be lowercased)
        normalized: The normalized status to map to
    """
    KNOWN_STATUS_MAPPINGS[status.lower().strip()] = normalized


def clear_llm_cache() -> None:
    """Clear the LLM status cache."""
    _llm_status_cache.clear()


def get_llm_cache() -> dict[str, NormalizedStatus]:
    """Get a copy of the current LLM cache contents."""
    return _llm_status_cache.copy()
