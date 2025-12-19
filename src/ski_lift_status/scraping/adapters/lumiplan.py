"""
Lumiplan/Lumiplay platform adapter.

Lumiplan is a common European ski resort management platform that provides
real-time lift and run status via REST APIs. Many resorts embed Lumiplay
interactive maps which fetch data from standardized endpoints.

Known API patterns:
- /interactive-map-services/public/map/name/{resort-slug}
- /interactive-map-services/public/map/{uuid}/staticPoiData
- /interactive-map-services/public/map/{uuid}/dynamicPoiData
"""

import re
from dataclasses import dataclass
from typing import Any

from ..models import CapturedResource
from ..logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class LumiplanLift:
    """Lift data from Lumiplan API."""

    id: int
    name: str
    lift_type: str | None
    station: str | None
    opening_status: str
    operating: bool | None
    # Additional fields
    opening_time: str | None = None
    closing_time: str | None = None
    wait_time_minutes: int | None = None
    # Lift metadata
    arrival_altitude: float | None = None
    departure_altitude: float | None = None
    capacity: int | None = None
    duration_minutes: float | None = None


@dataclass
class LumiplanTrail:
    """Trail/run data from Lumiplan API."""

    id: int
    name: str
    difficulty: str | None
    station: str | None
    opening_status: str
    grooming_status: str | None
    # Additional fields
    opening_time: str | None = None
    closing_time: str | None = None
    snow_condition: str | None = None


@dataclass
class LumiplanData:
    """Extracted data from Lumiplan APIs."""

    lifts: list[LumiplanLift]
    trails: list[LumiplanTrail]
    map_uuid: str | None = None


# URL patterns that indicate Lumiplan platform
URL_PATTERNS: list[str] = [
    r"lumiplay\.link/interactive-map",
    r"lumiplan\.com/api",
    r"lumiplan\.pro/api",
    r"/interactive-map-services/public/map/",
]


def detect(resources: list[CapturedResource]) -> bool:
    """Check if any resources match Lumiplan platform patterns."""
    for resource in resources:
        for pattern in URL_PATTERNS:
            if re.search(pattern, resource.url, re.IGNORECASE):
                return True
    return False


def find_api_resources(
    resources: list[CapturedResource],
) -> tuple[CapturedResource | None, CapturedResource | None]:
    """Find staticPoiData and dynamicPoiData resources."""
    static_resource = None
    dynamic_resource = None

    for resource in resources:
        if "staticPoiData" in resource.url:
            static_resource = resource
        elif "dynamicPoiData" in resource.url:
            dynamic_resource = resource

    return static_resource, dynamic_resource


def extract_map_uuid(resources: list[CapturedResource]) -> str | None:
    """Extract the map UUID from API URLs."""
    pattern = r"/map/([a-f0-9-]{36})/"
    for resource in resources:
        match = re.search(pattern, resource.url)
        if match:
            return match.group(1)
    return None


def parse_static_data(content: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Parse staticPoiData JSON into a lookup by data.id."""
    items = content.get("items", [])
    result = {}

    for item in items:
        data = item.get("data", {})
        data_id = data.get("id")
        if data_id:
            result[data_id] = data

    return result


def parse_dynamic_data(content: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Parse dynamicPoiData JSON into a lookup by id."""
    items = content.get("items", [])
    return {item["id"]: item for item in items if "id" in item}


def extract_opening_times(static_item: dict[str, Any]) -> tuple[str | None, str | None]:
    """Extract opening and closing times from static POI data.

    Args:
        static_item: The static data dict for a lift/trail

    Returns:
        Tuple of (opening_time, closing_time) in HH:MM format, or None if not available
    """
    theoretic_times = static_item.get("openingTimesTheoretic", [])
    if theoretic_times and isinstance(theoretic_times, list) and len(theoretic_times) > 0:
        first_slot = theoretic_times[0]
        return first_slot.get("beginTime"), first_slot.get("endTime")
    return None, None


def extract(resources: list[CapturedResource]) -> LumiplanData | None:
    """Extract lift/run data from Lumiplan API responses.

    Args:
        resources: List of captured network resources

    Returns:
        LumiplanData with extracted lifts and trails, or None if extraction fails
    """
    log = logger.bind(adapter="lumiplan")

    static_resource, dynamic_resource = find_api_resources(resources)

    if not static_resource:
        log.warning("no_static_poi_data", msg="staticPoiData resource not found")
        return None

    if not dynamic_resource:
        log.warning("no_dynamic_poi_data", msg="dynamicPoiData resource not found")
        return None

    try:
        import json

        static_data = parse_static_data(json.loads(static_resource.content or "{}"))
        dynamic_data = parse_dynamic_data(json.loads(dynamic_resource.content or "{}"))
    except (json.JSONDecodeError, AttributeError) as e:
        log.error("parse_error", error=str(e))
        return None

    map_uuid = extract_map_uuid(resources)
    lifts = []
    trails = []

    for data_id, static_item in static_data.items():
        item_type = static_item.get("type")
        dynamic_item = dynamic_data.get(data_id, {})
        opening_time, closing_time = extract_opening_times(static_item)

        if item_type == "LIFT":
            lifts.append(
                LumiplanLift(
                    id=data_id,
                    name=static_item.get("name", ""),
                    lift_type=static_item.get("liftType"),
                    station=static_item.get("station") or static_item.get("stationName"),
                    opening_status=dynamic_item.get("openingStatus", "unknown"),
                    operating=dynamic_item.get("operating"),
                    opening_time=opening_time,
                    closing_time=closing_time,
                    wait_time_minutes=dynamic_item.get("waitTime"),
                    arrival_altitude=static_item.get("arrivalAltitude"),
                    departure_altitude=static_item.get("departureAltitude"),
                    capacity=static_item.get("capacity"),
                    duration_minutes=static_item.get("duration"),
                )
            )
        elif item_type == "TRAIL":
            trails.append(
                LumiplanTrail(
                    id=data_id,
                    name=static_item.get("name", ""),
                    difficulty=static_item.get("difficulty"),
                    station=static_item.get("station") or static_item.get("stationName"),
                    opening_status=dynamic_item.get("openingStatus", "unknown"),
                    grooming_status=dynamic_item.get("groomingStatus"),
                    opening_time=opening_time,
                    closing_time=closing_time,
                    snow_condition=dynamic_item.get("snowCondition"),
                )
            )

    log.info(
        "extraction_complete",
        lift_count=len(lifts),
        trail_count=len(trails),
        map_uuid=map_uuid,
    )

    return LumiplanData(lifts=lifts, trails=trails, map_uuid=map_uuid)


def get_status_summary(data: LumiplanData) -> dict[str, dict[str, int]]:
    """Get aggregate status counts for lifts and trails."""
    lift_status: dict[str, int] = {}
    trail_status: dict[str, int] = {}

    for lift in data.lifts:
        status = lift.opening_status
        lift_status[status] = lift_status.get(status, 0) + 1

    for trail in data.trails:
        status = trail.opening_status
        trail_status[status] = trail_status.get(status, 0) + 1

    return {"lifts": lift_status, "trails": trail_status}


# =============================================================================
# HTTP-Only Fetching (for config execution - no browser needed)
# =============================================================================

async def fetch_live_status(map_uuid: str) -> LumiplanData | None:
    """Fetch live status data directly via HTTP.

    This is the HTTP-only execution path - NO browser automation.
    Use this when you already know the map_uuid from a saved config.

    Args:
        map_uuid: The Lumiplan map UUID (e.g., "bd632c91-6957-494d-95a8-6a72eb87e341")

    Returns:
        LumiplanData with extracted lifts and trails, or None if fetch fails
    """
    import json
    import httpx

    log = logger.bind(adapter="lumiplan", map_uuid=map_uuid)

    base_url = f"https://lumiplay.link/interactive-map-services/public/map/{map_uuid}"
    static_url = f"{base_url}/staticPoiData?lang=fr"
    dynamic_url = f"{base_url}/dynamicPoiData?lang=fr"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Fetch both endpoints
            log.debug("fetching_static_data", url=static_url)
            static_resp = await client.get(static_url, headers=headers)
            static_resp.raise_for_status()

            log.debug("fetching_dynamic_data", url=dynamic_url)
            dynamic_resp = await client.get(dynamic_url, headers=headers)
            dynamic_resp.raise_for_status()

            static_data = parse_static_data(static_resp.json())
            dynamic_data = parse_dynamic_data(dynamic_resp.json())

    except httpx.HTTPError as e:
        log.error("http_error", error=str(e))
        return None
    except json.JSONDecodeError as e:
        log.error("json_parse_error", error=str(e))
        return None

    lifts = []
    trails = []

    for data_id, static_item in static_data.items():
        item_type = static_item.get("type")
        dynamic_item = dynamic_data.get(data_id, {})
        opening_time, closing_time = extract_opening_times(static_item)

        if item_type == "LIFT":
            lifts.append(
                LumiplanLift(
                    id=data_id,
                    name=static_item.get("name", ""),
                    lift_type=static_item.get("liftType"),
                    station=static_item.get("station") or static_item.get("stationName"),
                    opening_status=dynamic_item.get("openingStatus", "unknown"),
                    operating=dynamic_item.get("operating"),
                    opening_time=opening_time,
                    closing_time=closing_time,
                    wait_time_minutes=dynamic_item.get("waitTime"),
                    arrival_altitude=static_item.get("arrivalAltitude"),
                    departure_altitude=static_item.get("departureAltitude"),
                    capacity=static_item.get("capacity"),
                    duration_minutes=static_item.get("duration"),
                )
            )
        elif item_type == "TRAIL":
            trails.append(
                LumiplanTrail(
                    id=data_id,
                    name=static_item.get("name", ""),
                    difficulty=static_item.get("difficulty"),
                    station=static_item.get("station") or static_item.get("stationName"),
                    opening_status=dynamic_item.get("openingStatus", "unknown"),
                    grooming_status=dynamic_item.get("groomingStatus"),
                    opening_time=opening_time,
                    closing_time=closing_time,
                    snow_condition=dynamic_item.get("snowCondition"),
                )
            )

    log.info(
        "fetch_complete",
        lift_count=len(lifts),
        trail_count=len(trails),
    )

    return LumiplanData(lifts=lifts, trails=trails, map_uuid=map_uuid)
