"""
Intermaps platform adapter.

Intermaps provides interactive ski maps for many European ski resorts.
Their data API provides lift and slope status information.

Known resorts using Intermaps:
- Portes du Soleil (Les Gets, Morzine, Avoriaz, Châtel, etc.)
- And others

API Endpoint pattern:
- https://winter.intermaps.com/{resort_slug}/data?lang=en

Extraction approach:
1. Fetch the JSON data from the API endpoint
2. Parse lift and trail objects from the response
3. Extract names, statuses, and metadata
"""

import re
from dataclasses import dataclass

import httpx
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class IntermapsLift:
    """Lift data from Intermaps."""
    name: str
    status: str | None
    lift_type: str | None = None
    length_m: int | None = None
    capacity: int | None = None
    altitude_bottom: int | None = None
    altitude_top: int | None = None


@dataclass
class IntermapsTrail:
    """Trail data from Intermaps."""
    name: str
    status: str | None
    difficulty: str | None = None
    length_m: int | None = None


@dataclass
class IntermapsData:
    """Extracted data from Intermaps."""
    lifts: list[IntermapsLift]
    trails: list[IntermapsTrail]
    resort_slug: str | None = None


# Status mapping from Intermaps status IDs
STATUS_MAP = {
    "open": "open",
    "closed": "closed",
    "closed_outoforder": "closed",
    "closed_atmos": "closed",
    "closed_prep": "expected_to_open",  # In preparation
    "closed_seasonal": "not_expected_to_open",
    "unknown": "unknown",
}


# Lift type mapping based on client-sub-id values
LIFT_TYPE_MAP = {
    "2607": "T-bar",
    "2608": "aerial_tramway",
    "2610": "magic_carpet",
    "2613": "handle_tow",
    "2614": "3-chair",
    "2615": "4-chair",
    "2616": "6-chair",
    "2617": "8-chair",
    "2621": "gondola",
    "2622": "funicular",
    "2625": "cable_car",
}


def _parse_lift_data(data: dict) -> list[IntermapsLift]:
    """Parse lift data from Intermaps JSON response.

    The structure is:
    {
        "lifts": [
            {
                "popup": {"title": "TSK BARMETTES", "subtitle": "T-bar", "additional-info": {...}},
                "status": "closed",
                "type": 2607,
                "subtitle": "T-bar"
            }
        ]
    }

    Args:
        data: The JSON response dict

    Returns:
        List of parsed lifts
    """
    lifts: list[IntermapsLift] = []

    lifts_data = data.get("lifts", [])

    for lift_obj in lifts_data:
        if not isinstance(lift_obj, dict):
            continue

        # Get name from popup.title
        popup = lift_obj.get("popup", {})
        name = popup.get("title", "")
        if not name:
            continue

        # Get status
        status_raw = lift_obj.get("status", "unknown")
        status = STATUS_MAP.get(str(status_raw).lower(), "unknown")

        # Get lift type from subtitle or type code
        lift_type = lift_obj.get("subtitle") or popup.get("subtitle")
        type_code = str(lift_obj.get("type", ""))
        if not lift_type and type_code in LIFT_TYPE_MAP:
            lift_type = LIFT_TYPE_MAP[type_code]

        # Get additional info
        additional = popup.get("additional-info", {})
        length_m = additional.get("length")
        capacity = additional.get("capacity")

        lifts.append(IntermapsLift(
            name=name,
            status=status,
            lift_type=lift_type,
            length_m=length_m,
            capacity=capacity,
        ))

    # Deduplicate by name
    seen_names: set[str] = set()
    unique_lifts = []
    for lift in lifts:
        if lift.name not in seen_names:
            seen_names.add(lift.name)
            unique_lifts.append(lift)

    return unique_lifts


def _parse_trail_data(data: dict) -> list[IntermapsTrail]:
    """Parse trail data from Intermaps JSON response.

    The structure is:
    {
        "slopes": [
            {
                "popup": {"title": "JEAN VUARNET", "subtitle": "slope (medium)", "additional-info": {...}},
                "status": "closed",
                "subtitle": "slope (medium)"
            }
        ]
    }

    Args:
        data: The JSON response dict

    Returns:
        List of parsed trails
    """
    trails: list[IntermapsTrail] = []

    trails_data = data.get("slopes", [])

    for trail_obj in trails_data:
        if not isinstance(trail_obj, dict):
            continue

        # Get name from popup.title
        popup = trail_obj.get("popup", {})
        name = popup.get("title", "")
        if not name:
            continue

        # Get status
        status_raw = trail_obj.get("status", "unknown")
        status = STATUS_MAP.get(str(status_raw).lower(), "unknown")

        # Get difficulty from subtitle
        subtitle = trail_obj.get("subtitle") or popup.get("subtitle") or ""
        difficulty = None
        subtitle_lower = subtitle.lower()
        if "easy" in subtitle_lower or "green" in subtitle_lower:
            difficulty = "easy"
        elif "medium" in subtitle_lower or "blue" in subtitle_lower:
            difficulty = "intermediate"
        elif "hard" in subtitle_lower or "red" in subtitle_lower or "difficult" in subtitle_lower:
            difficulty = "advanced"
        elif "expert" in subtitle_lower or "black" in subtitle_lower:
            difficulty = "expert"

        # Get additional info
        additional = popup.get("additional-info", {})
        length_m = additional.get("length")

        trails.append(IntermapsTrail(
            name=name,
            status=status,
            difficulty=difficulty,
            length_m=length_m,
        ))

    return trails


async def fetch_intermaps_status(resort_slug: str) -> IntermapsData | None:
    """Fetch live status data from Intermaps.

    This is the HTTP-only execution path - NO browser automation.

    Args:
        resort_slug: The Intermaps resort identifier (e.g., "portes_du_soleil")

    Returns:
        IntermapsData with extracted lifts and trails, or None if fetch fails
    """
    log = logger.bind(adapter="intermaps", resort_slug=resort_slug)

    url = f"https://winter.intermaps.com/{resort_slug}/data?lang=en"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json,text/html,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            log.debug("fetching_data", url=url)
            response = await client.get(url, headers=headers)
            response.raise_for_status()

            data = response.json()

    except httpx.HTTPError as e:
        log.error("http_error", error=str(e))
        return None
    except Exception as e:
        log.error("parse_error", error=str(e))
        return None

    if not data:
        log.warning("empty_response")
        return None

    lifts = _parse_lift_data(data)
    trails = _parse_trail_data(data)

    log.info(
        "fetch_complete",
        lift_count=len(lifts),
        trail_count=len(trails),
    )

    return IntermapsData(lifts=lifts, trails=trails, resort_slug=resort_slug)
