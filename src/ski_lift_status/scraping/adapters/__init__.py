"""
Platform adapters for ski resort data extraction.

Each adapter handles a specific backend platform used by ski resorts.
Adapters provide:
- detect(): Check if captured resources match this platform
- extract(): Extract structured lift/run data from resources
- get_status_summary(): Get aggregate status counts

Usage:
    from ski_lift_status.scraping.adapters import detect_platform, extract_with_adapter

    platform = detect_platform(resources)
    if platform:
        data = extract_with_adapter(platform, resources)
"""

from typing import Any

from ..models import CapturedResource
from . import lumiplan, skiplan, nuxtjs

# Registry of available adapters
# NOTE: Adapters should be platform/technology-based, NOT resort-specific
ADAPTERS = {
    "lumiplan": lumiplan,  # Common European resort platform
    "skiplan": skiplan,     # Resort management system
    "nuxtjs": nuxtjs,       # Nuxt.js __NUXT__ payload extraction
}


def detect_platform(resources: list[CapturedResource]) -> str | None:
    """Detect which platform the resources are from.

    Args:
        resources: List of captured network resources

    Returns:
        Platform name if detected, None otherwise
    """
    for name, adapter in ADAPTERS.items():
        if adapter.detect(resources):
            return name
    return None


def extract_with_adapter(
    platform: str, resources: list[CapturedResource]
) -> Any | None:
    """Extract data using the appropriate platform adapter.

    Args:
        platform: Platform name (from detect_platform)
        resources: List of captured network resources

    Returns:
        Platform-specific data object, or None if extraction fails
    """
    if platform not in ADAPTERS:
        return None

    adapter = ADAPTERS[platform]
    return adapter.extract(resources)


def get_status_summary(platform: str, data: Any) -> dict[str, dict[str, int]] | None:
    """Get status summary from extracted data.

    Args:
        platform: Platform name
        data: Extracted data from extract_with_adapter

    Returns:
        Dict with 'lifts' and 'trails' status counts
    """
    if platform not in ADAPTERS:
        return None

    adapter = ADAPTERS[platform]
    return adapter.get_status_summary(data)


__all__ = [
    "detect_platform",
    "extract_with_adapter",
    "get_status_summary",
    "lumiplan",
    "skiplan",
    "nuxtjs",
]
