"""Status word finder for identifying dynamic status data.

This module finds resources containing status-related words in multiple
languages (English, French, German, Italian) to identify files with
dynamic lift/run status data.
"""

import re
from dataclasses import dataclass, field
from typing import Any


# Lift indicator words in multiple ski-region languages
LIFT_INDICATOR_WORDS = {
    # English
    "lift", "chairlift", "chair lift", "gondola", "cable car", "funicular",
    "t-bar", "t bar", "drag lift", "magic carpet", "surface lift",
    "quad", "triple", "double", "six-pack", "eight-pack",
    # French
    "télésiège", "telesiege", "télécabine", "telecabine", "téléski", "teleski",
    "télémix", "telemix", "téléphérique", "telepherique", "remontée", "remontee",
    "tire-fesse", "fil neige",
    # German
    "sessellift", "sesselbahn", "gondelbahn", "seilbahn", "skilift",
    "schlepplift", "tellerlift", "ankerlift", "förderband",
    # Italian
    "seggiovia", "cabinovia", "funivia", "funicolare", "skilift",
    "tapis roulant", "manovia",
    # Spanish
    "telesilla", "telecabina", "teleférico", "funicular",
}

# Run/piste indicator words in multiple languages
RUN_INDICATOR_WORDS = {
    # English
    "run", "slope", "trail", "piste", "course", "terrain",
    # French
    "piste", "descente", "parcours",
    # German
    "piste", "abfahrt", "skipiste", "loipe",
    # Italian
    "pista", "discesa",
    # Spanish
    "pista",
}

# Status words indicating open/closed/etc state
STATUS_WORDS = {
    # Open statuses
    "open": "open",
    "ouvert": "open",
    "ouverte": "open",
    "geöffnet": "open",
    "geoffnet": "open",
    "aperto": "open",
    "aperta": "open",
    "abierto": "open",
    "abierta": "open",
    "in operation": "open",
    "operating": "open",
    "en service": "open",

    # Closed statuses
    "closed": "closed",
    "fermé": "closed",
    "ferme": "closed",
    "fermée": "closed",
    "fermee": "closed",
    "geschlossen": "closed",
    "chiuso": "closed",
    "chiusa": "closed",
    "cerrado": "closed",
    "cerrada": "closed",
    "not operating": "closed",
    "hors service": "closed",

    # Hold/standby statuses
    "hold": "hold",
    "standby": "hold",
    "on hold": "hold",
    "pause": "hold",
    "attente": "hold",
    "wartend": "hold",

    # Groomed statuses (for runs)
    "groomed": "groomed",
    "damé": "groomed",
    "dame": "groomed",
    "präpariert": "groomed",
    "prapariert": "groomed",
    "preparata": "groomed",
    "preparato": "groomed",

    # Wind hold
    "wind hold": "wind_hold",
    "vent": "wind_hold",
    "vento": "wind_hold",

    # Scheduled
    "scheduled": "scheduled",
    "planifié": "scheduled",
    "geplant": "scheduled",
}


@dataclass
class StatusMatch:
    """A status word match found in content."""

    word: str
    normalized_status: str  # Normalized to English
    position: int
    context: str
    language: str  # Detected language


@dataclass
class StatusFinderResult:
    """Result of analyzing a resource for status indicators."""

    resource_url: str
    lift_indicator_count: int = 0
    run_indicator_count: int = 0
    status_word_count: int = 0
    status_matches: list[StatusMatch] = field(default_factory=list)
    likely_contains_lift_status: bool = False
    likely_contains_run_status: bool = False
    score: float = 0.0  # Combined relevance score

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "resource_url": self.resource_url,
            "lift_indicator_count": self.lift_indicator_count,
            "run_indicator_count": self.run_indicator_count,
            "status_word_count": self.status_word_count,
            "status_matches": [
                {
                    "word": m.word,
                    "normalized_status": m.normalized_status,
                    "position": m.position,
                    "context": m.context,
                    "language": m.language,
                }
                for m in self.status_matches
            ],
            "likely_contains_lift_status": self.likely_contains_lift_status,
            "likely_contains_run_status": self.likely_contains_run_status,
            "score": self.score,
        }


def _extract_context(content: str, position: int, context_size: int = 40) -> str:
    """Extract surrounding context from content."""
    start = max(0, position - context_size)
    end = min(len(content), position + context_size)
    context = content[start:end]
    return re.sub(r'\s+', ' ', context).strip()


def _detect_language(word: str) -> str:
    """Detect likely language of a status word."""
    word_lower = word.lower()

    # French patterns
    if word_lower in {"ouvert", "ouverte", "fermé", "ferme", "fermée", "fermee",
                      "damé", "dame", "télésiège", "télécabine", "planifié"}:
        return "french"

    # German patterns
    if word_lower in {"geöffnet", "geoffnet", "geschlossen", "präpariert",
                      "sessellift", "geplant", "wartend"}:
        return "german"

    # Italian patterns
    if word_lower in {"aperto", "aperta", "chiuso", "chiusa", "seggiovia",
                      "cabinovia", "preparata", "preparato"}:
        return "italian"

    # Spanish patterns
    if word_lower in {"abierto", "abierta", "cerrado", "cerrada", "telesilla"}:
        return "spanish"

    return "english"


def find_status_indicators(content: str) -> StatusFinderResult:
    """Find lift/run indicator words and status words in content.

    Args:
        content: The text content to search.

    Returns:
        StatusFinderResult with counts and matches.
    """
    result = StatusFinderResult(resource_url="")
    content_lower = content.lower()

    # Count lift indicator words
    for word in LIFT_INDICATOR_WORDS:
        count = len(re.findall(r'\b' + re.escape(word) + r'\b', content_lower))
        result.lift_indicator_count += count

    # Count run indicator words
    for word in RUN_INDICATOR_WORDS:
        count = len(re.findall(r'\b' + re.escape(word) + r'\b', content_lower))
        result.run_indicator_count += count

    # Find status words and their positions
    for word, normalized in STATUS_WORDS.items():
        pattern = r'\b' + re.escape(word) + r'\b'
        for match in re.finditer(pattern, content_lower):
            result.status_matches.append(StatusMatch(
                word=word,
                normalized_status=normalized,
                position=match.start(),
                context=_extract_context(content, match.start()),
                language=_detect_language(word),
            ))

    result.status_word_count = len(result.status_matches)

    # Determine if this resource likely contains lift/run status
    # Heuristic: needs both indicator words AND status words
    result.likely_contains_lift_status = (
        result.lift_indicator_count >= 2 and result.status_word_count >= 3
    )
    result.likely_contains_run_status = (
        result.run_indicator_count >= 2 and result.status_word_count >= 3
    )

    # Calculate combined score
    # Higher weight for status words as they're more specific
    result.score = (
        result.lift_indicator_count * 1.0 +
        result.run_indicator_count * 1.0 +
        result.status_word_count * 3.0
    )

    return result


def analyze_resources_for_status(
    resources: list[dict],  # List of CapturedResource.to_dict()
) -> list[StatusFinderResult]:
    """Analyze multiple resources for status indicators.

    Args:
        resources: List of captured resource dictionaries.

    Returns:
        List of StatusFinderResult, sorted by score (highest first).
    """
    results: list[StatusFinderResult] = []

    for resource in resources:
        body = resource.get("body", "")
        url = resource.get("url", "")

        if not body:
            continue

        result = find_status_indicators(body)
        result.resource_url = url
        results.append(result)

    # Sort by score (highest first)
    results.sort(key=lambda r: r.score, reverse=True)

    return results
