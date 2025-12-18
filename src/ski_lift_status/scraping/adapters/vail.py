"""
Vail Resorts platform adapter.

Vail Resorts owns many ski resorts including:
- Breckenridge, Vail, Beaver Creek, Keystone (Colorado)
- Park City (Utah)
- Whistler Blackcomb (BC, Canada)
- Stowe, Okemo (Vermont)
- And many others

Their websites embed lift/terrain status in a JavaScript object called
`TerrainStatusFeed` which is included in a script tag on the page.

Extraction approach:
1. Fetch the terrain-and-lift-status.aspx page
2. Find the script containing "TerrainStatusFeed = {"
3. Parse the JavaScript object to extract lift names and statuses
4. Status codes are numeric: 0=closed, 1=open, 2=hold, 3=scheduled

Based on the parsing logic from: https://github.com/pirxpilot/liftie
"""

import re
import json
from dataclasses import dataclass

import httpx
import structlog
from bs4 import BeautifulSoup

logger = structlog.get_logger(__name__)


@dataclass
class VailLift:
    """Lift data from Vail Resorts."""
    name: str
    status: str | None
    lift_type: str | None = None
    wait_time: int | None = None
    opening_time: str | None = None
    closing_time: str | None = None


@dataclass
class VailTrail:
    """Trail data from Vail Resorts."""
    name: str
    status: str | None
    difficulty: str | None = None
    grooming: str | None = None
    opening_time: str | None = None
    closing_time: str | None = None


@dataclass
class VailData:
    """Extracted data from Vail Resorts."""
    lifts: list[VailLift]
    trails: list[VailTrail]
    resort_name: str | None = None


# Status code mapping (from Liftie: lib/tools/vail.js)
STATUS_MAP = {
    0: "closed",
    1: "open",
    2: "hold",
    3: "scheduled",
}


def _extract_terrain_status_feed(html: str) -> dict | None:
    """Extract the TerrainStatusFeed JavaScript object from HTML.

    Args:
        html: The HTML content of the page

    Returns:
        Parsed dict from the TerrainStatusFeed object, or None if not found
    """
    log = logger.bind(adapter="vail")

    # Find the script containing TerrainStatusFeed
    # Pattern: TerrainStatusFeed = {...}
    pattern = r'TerrainStatusFeed\s*=\s*(\{[^;]+\});'

    match = re.search(pattern, html, re.DOTALL)
    if not match:
        log.debug("terrain_status_feed_not_found")
        return None

    js_object = match.group(1)

    # Try to parse as JSON - may need some cleanup
    try:
        # The object might not be valid JSON (single quotes, trailing commas)
        # Try to clean it up

        # Replace single quotes with double quotes (careful with nested quotes)
        # This is a simple approach - might need refinement
        cleaned = js_object

        # Try direct JSON parse first
        return json.loads(cleaned)
    except json.JSONDecodeError:
        log.debug("json_parse_failed_trying_cleanup")

    # Try alternative approach: use regex to extract key-value pairs
    # For lift status, we mainly need the Lifts array
    lifts_pattern = r'"?Lifts"?\s*:\s*\[([^\]]+)\]'
    lifts_match = re.search(lifts_pattern, html, re.DOTALL)

    if lifts_match:
        lifts_str = lifts_match.group(1)
        # Try to parse individual lift objects
        lift_pattern = r'\{[^}]+\}'
        lift_objects = re.findall(lift_pattern, lifts_str)

        lifts = []
        for obj_str in lift_objects:
            # Extract name and status
            name_match = re.search(r'"?Name"?\s*:\s*"([^"]+)"', obj_str)
            status_match = re.search(r'"?Status"?\s*:\s*(\d)', obj_str)

            if name_match:
                lift = {"Name": name_match.group(1)}
                if status_match:
                    lift["Status"] = int(status_match.group(1))
                lifts.append(lift)

        if lifts:
            return {"Lifts": lifts}

    return None


def _parse_terrain_data(data: dict) -> tuple[list[VailLift], list[VailTrail]]:
    """Parse the TerrainStatusFeed data into lift and trail objects.

    Args:
        data: Parsed TerrainStatusFeed dict

    Returns:
        Tuple of (lifts, trails)
    """
    lifts: list[VailLift] = []
    trails: list[VailTrail] = []

    # Parse lifts
    lifts_data = data.get("Lifts", [])
    for lift_obj in lifts_data:
        if not isinstance(lift_obj, dict):
            continue

        name = lift_obj.get("Name", "")
        if not name:
            continue

        status_code = lift_obj.get("Status", 0)
        status = STATUS_MAP.get(status_code, "closed")

        # Extract additional data if available
        wait_time = lift_obj.get("WaitTime") or lift_obj.get("WaitTimeMinutes")
        lift_type = lift_obj.get("Type") or lift_obj.get("LiftType")

        lifts.append(VailLift(
            name=name,
            status=status,
            lift_type=lift_type,
            wait_time=int(wait_time) if wait_time else None,
        ))

    # Parse trails if present
    trails_data = data.get("Trails", []) or data.get("Runs", [])
    for trail_obj in trails_data:
        if not isinstance(trail_obj, dict):
            continue

        name = trail_obj.get("Name", "")
        if not name:
            continue

        status_code = trail_obj.get("Status", 0)
        status = STATUS_MAP.get(status_code, "closed")

        difficulty = trail_obj.get("Difficulty") or trail_obj.get("Rating")
        grooming = trail_obj.get("GroomingStatus") or trail_obj.get("Grooming")

        trails.append(VailTrail(
            name=name,
            status=status,
            difficulty=difficulty,
            grooming=grooming,
        ))

    return lifts, trails


def _parse_html_fallback(html: str) -> tuple[list[VailLift], list[VailTrail]]:
    """Fallback HTML parsing using BeautifulSoup.

    Some Vail resort pages may have data in a different format.
    This tries to extract lift info from visible HTML elements.

    Args:
        html: The HTML content

    Returns:
        Tuple of (lifts, trails)
    """
    soup = BeautifulSoup(html, "lxml")
    lifts: list[VailLift] = []
    trails: list[VailTrail] = []

    # Look for lift status elements (common patterns)
    # Pattern 1: Elements with data-lift-name or similar attributes
    lift_elements = soup.select("[data-lift-name], [data-name], .lift-item, .lift-status-item")

    for elem in lift_elements:
        name = elem.get("data-lift-name") or elem.get("data-name")
        if not name:
            name_elem = elem.select_one(".lift-name, .name")
            if name_elem:
                name = name_elem.get_text(strip=True)

        if not name:
            continue

        # Try to get status
        status = "closed"
        status_elem = elem.select_one(".lift-status, .status")
        if status_elem:
            status_text = status_elem.get_text(strip=True).lower()
            if "open" in status_text:
                status = "open"
            elif "hold" in status_text:
                status = "hold"
            elif "scheduled" in status_text:
                status = "scheduled"

        lifts.append(VailLift(name=name, status=status))

    return lifts, trails


async def fetch_vail_status(resort_url: str) -> VailData | None:
    """Fetch live status data from a Vail Resorts property.

    This is the HTTP-only execution path - NO browser automation.

    Args:
        resort_url: The URL to the terrain-and-lift-status.aspx page

    Returns:
        VailData with extracted lifts and trails, or None if fetch fails
    """
    log = logger.bind(adapter="vail", url=resort_url[:50])

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            log.debug("fetching_page")
            response = await client.get(resort_url, headers=headers)
            response.raise_for_status()
            html = response.text

    except httpx.HTTPError as e:
        log.error("http_error", error=str(e))
        return None

    if not html:
        log.warning("empty_response")
        return None

    # Try to extract TerrainStatusFeed
    terrain_data = _extract_terrain_status_feed(html)

    if terrain_data:
        lifts, trails = _parse_terrain_data(terrain_data)
        log.info(
            "fetch_complete",
            lift_count=len(lifts),
            trail_count=len(trails),
            method="terrain_status_feed",
        )
        return VailData(lifts=lifts, trails=trails)

    # Fallback to HTML parsing
    log.debug("terrain_status_feed_not_found_trying_html_fallback")
    lifts, trails = _parse_html_fallback(html)

    if lifts or trails:
        log.info(
            "fetch_complete",
            lift_count=len(lifts),
            trail_count=len(trails),
            method="html_fallback",
        )
        return VailData(lifts=lifts, trails=trails)

    log.warning("no_data_extracted")
    return None


# Convenience function for Breckenridge
async def fetch_breckenridge() -> VailData | None:
    """Fetch Breckenridge lift/trail status."""
    return await fetch_vail_status(
        "https://www.breckenridge.com/the-mountain/mountain-conditions/terrain-and-lift-status.aspx"
    )
